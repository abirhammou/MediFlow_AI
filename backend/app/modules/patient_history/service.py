"""AI medical summaries (whole history or one report) and the patient chat, for doctors.

Both read only `context.collect_sources` (reports, MEDICAL file text, notes for the
chat), masked. Long histories are summarized in two steps: notes per chunk of
sources (map), then the final text from those notes (reduce). Summaries follow the
patient_summaries workflow (DRAFT -> VALIDATED / REJECTED, previous VALIDATED ->
SUPERSEDED); chat answers are not stored, only logged in llm_interactions.
"""

import json
import re
from datetime import timedelta
from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import NE, Eq, In, Set
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.core.time import utcnow
from app.errors import APIError, LLMResponseError
from app.llm.client import complete
from app.llm.interactions import count_interactions
from app.modules.auth.models import User
from app.modules.auth.repository import get_user_names
from app.modules.llm.models import LlmModule
from app.modules.patient_history.context import (
    Source,
    collect_sources,
    patient_profile,
    same_sources,
)
from app.modules.patient_history.models import (
    HISTORY_MAX_LENGTH,
    HistoryScope,
    PatientHistorySummary,
)
from app.modules.patient_history.prompts import (
    NOT_FOUND_ANSWER,
    PROMPT_VERSION,
    REPORT_PROMPT,
    TIMELINE_PROMPT,
    chat_messages,
    map_messages,
    summary_messages,
)
from app.modules.patient_history.schemas import (
    ChatAnswer,
    ChatRequest,
    ChatSource,
    HistoryGenerate,
    HistoryReject,
    HistorySummaryOut,
    HistoryUpdate,
)
from app.modules.patients import repository as patients
from app.modules.patients.models import Patient, SummaryStatus

# Above this many characters of sources, they are condensed first (map step).
CONTEXT_LIMIT = 12_000
CHUNK_LIMIT = 8_000
# LLM calls per user and hour (a long history costs several calls).
SUMMARY_CALLS_PER_HOUR = 20
CHAT_CALLS_PER_HOUR = 40
CODE_FENCE = re.compile(r"^[ \t]*```[\w-]*[ \t]*$\n?", re.MULTILINE)
CITATION = re.compile(r"\[(S\d+)\]")


def _object_id(value: str | None, code: str, detail: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError):
        raise APIError(404, code, detail) from None


async def _patient(patient_id: str) -> Patient:
    pid = _object_id(patient_id, "patient_not_found", "Dossier patient introuvable.")
    patient = await patients.get_patient(pid)
    if patient is None:
        raise APIError(404, "patient_not_found", "Dossier patient introuvable.")
    return patient


async def _check_quota(module: LlmModule, user: User, limit: int) -> None:
    assert user.id is not None
    if await count_interactions(module, user.id, utcnow() - timedelta(hours=1)) >= limit:
        raise APIError(
            429,
            "ai_rate_limited",
            "Limite d'utilisation de l'IA atteinte pour cette heure. Réessayez plus tard.",
        )


def _chunks(sources: list[Source]) -> list[list[Source]]:
    """Groups of at most CHUNK_LIMIT characters; a longer source is cut in parts."""
    pieces = [
        Source(s.id, s.kind, s.ref_id, s.label, s.date, s.text[start : start + CHUNK_LIMIT])
        for s in sources
        for start in range(0, len(s.text), CHUNK_LIMIT)
    ]
    groups: list[list[Source]] = [[]]
    size = 0
    for piece in pieces:
        if groups[-1] and size + len(piece.text) > CHUNK_LIMIT:
            groups.append([])
            size = 0
        groups[-1].append(piece)
        size += len(piece.text)
    return groups


def _not_empty(text: str) -> str:
    text = CODE_FENCE.sub("", text).strip()
    if not text:
        raise LLMResponseError()
    return text


async def condense(
    sources: list[Source],
    profile: str,
    *,
    module: LlmModule,
    patient_id: PydanticObjectId,
    user_id: PydanticObjectId | None,
) -> list[str] | None:
    """Notes per chunk when the sources are too long for one prompt, else None."""
    if sum(len(source.text) for source in sources) <= CONTEXT_LIMIT:
        return None
    notes = []
    for chunk in _chunks(sources):
        result = await complete(
            module=module,
            messages=map_messages(chunk, profile),
            entity_id=patient_id,
            user_id=user_id,
            max_tokens=900,
            postprocess=_not_empty,
        )
        notes.append(result.text)
    return notes


def clean_history(text: str) -> str:
    text = _not_empty(text)
    if len(text) > HISTORY_MAX_LENGTH:
        raise APIError(
            502,
            "summary_too_long",
            f"La synthèse générée dépasse {HISTORY_MAX_LENGTH} caractères. Relancez la génération.",
        )
    return text


def parse_chat(text: str) -> str:
    """The JSON answer, checked and normalized (raises LLMResponseError -> 502)."""
    text = CODE_FENCE.sub("", text).strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1]) if start != -1 else None
    except json.JSONDecodeError:
        data = None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("found"), bool)
        or not isinstance(data.get("answer"), str)
    ):
        raise LLMResponseError()
    cited = data.get("sources")
    sources = [s for s in cited if isinstance(s, str)] if isinstance(cited, list) else []
    return json.dumps(
        {"found": data["found"], "answer": data["answer"].strip(), "sources": sources},
        ensure_ascii=False,
    )


def _source_out(source: Source | dict) -> ChatSource:
    if isinstance(source, Source):
        source = source.fingerprint
    return ChatSource(
        id=source.get("id") or "",
        kind=source.get("kind") or "",
        ref_id=source.get("refId"),
        label=source.get("label") or "",
    )


class HistorySummaryService:
    async def _sources(
        self, patient: Patient, scope: HistoryScope, report_id: PydanticObjectId | None
    ) -> list[Source]:
        if scope == HistoryScope.REPORT:
            return await collect_sources(patient, report_id=report_id)
        return await collect_sources(patient)

    async def _out(
        self, patient: Patient, summaries: list[PatientHistorySummary]
    ) -> list[HistorySummaryOut]:
        names = await get_user_names(
            {u for s in summaries for u in (s.generated_by, s.reviewed_by) if u is not None}
        )
        current: dict[tuple, list[Source]] = {}
        result = []
        for summary in summaries:
            key = (summary.scope, summary.report_id)
            if key not in current:
                current[key] = await self._sources(patient, summary.scope, summary.report_id)
            snapshot = summary.source_snapshot or {}
            saved = snapshot.get("sources") or []
            result.append(
                HistorySummaryOut(
                    id=str(summary.id),
                    patient_id=str(summary.patient_id),
                    scope=summary.scope,
                    report_id=str(summary.report_id) if summary.report_id else None,
                    content=summary.content,
                    status=summary.status,
                    llm_model=summary.llm_model,
                    prompt_version=snapshot.get("promptVersion"),
                    sources=[_source_out(s) for s in saved],
                    is_outdated=not same_sources(saved, current[key]),
                    generated_by=str(summary.generated_by) if summary.generated_by else None,
                    generated_by_name=names.get(summary.generated_by)
                    if summary.generated_by
                    else None,
                    reviewed_by=str(summary.reviewed_by) if summary.reviewed_by else None,
                    reviewed_by_name=names.get(summary.reviewed_by)
                    if summary.reviewed_by
                    else None,
                    reviewed_at=summary.reviewed_at,
                    review_comment=summary.review_comment,
                    created_at=summary.created_at,
                )
            )
        return result

    async def _one(self, patient: Patient, summary: PatientHistorySummary) -> HistorySummaryOut:
        return (await self._out(patient, [summary]))[0]

    async def _summary(self, patient: Patient, summary_id: str) -> PatientHistorySummary:
        sid = _object_id(summary_id, "summary_not_found", "Synthèse introuvable.")
        summary = await PatientHistorySummary.find_one(
            Eq(PatientHistorySummary.id, sid), Eq(PatientHistorySummary.patient_id, patient.id)
        )
        if summary is None:
            raise APIError(404, "summary_not_found", "Synthèse introuvable.")
        return summary

    async def generate(
        self, user: User, patient_id: str, data: HistoryGenerate
    ) -> HistorySummaryOut:
        patient = await _patient(patient_id)
        assert patient.id is not None
        report_id = None
        if data.scope == HistoryScope.REPORT:
            if not data.report_id:
                raise APIError(422, "report_required", "Indiquez le compte rendu à résumer.")
            report_id = _object_id(data.report_id, "report_not_found", "Compte rendu introuvable.")
        await _check_quota(LlmModule.PATIENT_HISTORY, user, SUMMARY_CALLS_PER_HOUR)

        sources = await self._sources(patient, data.scope, report_id)
        if not sources:
            if data.scope == HistoryScope.REPORT:
                raise APIError(404, "report_not_found", "Compte rendu introuvable pour ce patient.")
            raise APIError(
                409, "nothing_to_summarize", "Aucun compte rendu ni document médical à résumer."
            )
        profile = patient_profile(patient)
        notes = await condense(
            sources,
            profile,
            module=LlmModule.PATIENT_HISTORY,
            patient_id=patient.id,
            user_id=user.id,
        )
        prompt = REPORT_PROMPT if data.scope == HistoryScope.REPORT else TIMELINE_PROMPT
        result = await complete(
            module=LlmModule.PATIENT_HISTORY,
            messages=summary_messages(prompt, sources, profile, notes),
            entity_id=patient.id,
            user_id=user.id,
            max_tokens=1500,
            postprocess=clean_history,
        )
        summary = PatientHistorySummary(
            patient_id=patient.id,
            scope=data.scope,
            report_id=report_id,
            content=result.text,
            status=SummaryStatus.DRAFT,
            llm_model=result.model,
            source_snapshot={
                "promptVersion": PROMPT_VERSION,
                "condensed": notes is not None,
                "sources": [source.fingerprint for source in sources],
            },
            generated_by=user.id,
        )
        await summary.insert()
        return await self._one(patient, summary)

    async def list(
        self, patient_id: str, scope: HistoryScope | None, report_id: str | None
    ) -> list[HistorySummaryOut]:
        patient = await _patient(patient_id)
        query: list[Any] = [Eq(PatientHistorySummary.patient_id, patient.id)]
        if scope is not None:
            query.append(Eq(PatientHistorySummary.scope, scope))
        if report_id is not None:
            rid = _object_id(report_id, "report_not_found", "Compte rendu introuvable.")
            query.append(Eq(PatientHistorySummary.report_id, rid))
        summaries = (
            await PatientHistorySummary.find(*query)
            .sort(-PatientHistorySummary.created_at, -PatientHistorySummary.id)
            .to_list()
        )
        return await self._out(patient, summaries)

    async def _update_draft(
        self, summary: PatientHistorySummary, changes: dict[str, Any], action: str
    ) -> PatientHistorySummary:
        updated = await PatientHistorySummary.find_one(
            Eq(PatientHistorySummary.id, summary.id),
            In(PatientHistorySummary.status, [SummaryStatus.DRAFT]),
        ).update(Set(changes), response_type=UpdateResponse.NEW_DOCUMENT)
        if updated is None:
            raise APIError(409, "summary_not_draft", f"Seul un brouillon peut être {action}.")
        return updated

    async def update(
        self, patient_id: str, summary_id: str, data: HistoryUpdate
    ) -> HistorySummaryOut:
        patient = await _patient(patient_id)
        summary = await self._summary(patient, summary_id)
        updated = await self._update_draft(summary, {"content": data.content}, "modifié")
        return await self._one(patient, updated)

    async def reject(
        self, user: User, patient_id: str, summary_id: str, data: HistoryReject
    ) -> HistorySummaryOut:
        patient = await _patient(patient_id)
        summary = await self._summary(patient, summary_id)
        changes = {
            "status": SummaryStatus.REJECTED,
            "reviewedBy": user.id,
            "reviewedAt": utcnow(),
            "reviewComment": data.comment,
        }
        updated = await self._update_draft(summary, changes, "rejeté")
        return await self._one(patient, updated)

    async def validate(self, user: User, patient_id: str, summary_id: str) -> HistorySummaryOut:
        """1. the previous VALIDATED one of the same scope becomes SUPERSEDED; 2. this DRAFT
        becomes VALIDATED (unique index: a concurrent validation is a 409). Validating a
        VALIDATED summary again replays step 1, so a retry repairs a half-done validation."""
        patient = await _patient(patient_id)
        summary = await self._summary(patient, summary_id)
        if summary.status not in (SummaryStatus.DRAFT, SummaryStatus.VALIDATED):
            raise APIError(409, "summary_not_draft", "Seul un brouillon peut être validé.")
        await PatientHistorySummary.find(
            Eq(PatientHistorySummary.patient_id, patient.id),
            Eq(PatientHistorySummary.scope, summary.scope),
            Eq(PatientHistorySummary.report_id, summary.report_id),
            Eq(PatientHistorySummary.status, SummaryStatus.VALIDATED),
            NE(PatientHistorySummary.id, summary.id),
        ).update_many(Set({"status": SummaryStatus.SUPERSEDED}))
        if summary.status == SummaryStatus.DRAFT:
            changes = {
                "status": SummaryStatus.VALIDATED,
                "reviewedBy": user.id,
                "reviewedAt": utcnow(),
            }
            try:
                summary = await self._update_draft(summary, changes, "validé")
            except DuplicateKeyError:
                raise APIError(
                    409,
                    "summary_conflict",
                    "Une autre synthèse vient d'être validée pour ce patient. Rechargez la page.",
                ) from None
        return await self._one(patient, summary)


class PatientChatService:
    async def ask(self, user: User, patient_id: str, data: ChatRequest) -> ChatAnswer:
        patient = await _patient(patient_id)
        assert patient.id is not None
        await _check_quota(LlmModule.PATIENT_CHAT, user, CHAT_CALLS_PER_HOUR)
        sources = await collect_sources(patient, include_notes=True)
        if not sources:
            return ChatAnswer(found=False, answer=NOT_FOUND_ANSWER, sources=[], llm_model=None)

        profile = patient_profile(patient)
        notes = await condense(
            sources, profile, module=LlmModule.PATIENT_CHAT, patient_id=patient.id, user_id=user.id
        )
        history = [(turn.question, turn.answer) for turn in data.history]
        result = await complete(
            module=LlmModule.PATIENT_CHAT,
            messages=chat_messages(data.question, history, sources, profile, notes),
            entity_id=patient.id,
            user_id=user.id,
            max_tokens=1000,
            response_format={"type": "json_object"},
            postprocess=parse_chat,
        )
        answer = json.loads(result.text)
        by_id = {source.id: source for source in sources}
        cited_ids = dict.fromkeys(
            [*answer["sources"], *CITATION.findall(answer["answer"])]
        )  # ordered, no duplicates
        cited = [by_id[source_id] for source_id in cited_ids if source_id in by_id]
        # Grounded answers only: no existing source cited means "not found".
        if not answer["found"] or not cited or not answer["answer"]:
            return ChatAnswer(
                found=False, answer=NOT_FOUND_ANSWER, sources=[], llm_model=result.model
            )
        return ChatAnswer(
            found=True,
            answer=answer["answer"],
            sources=[_source_out(source) for source in cited],
            llm_model=result.model,
        )
