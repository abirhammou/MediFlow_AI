"""Demo AI medical summaries for doctors and patient chat logs (run by scripts.seed_modules).

Built like app.modules.patient_history.service does, without calling an LLM: the
sources come from `collect_sources` (reports and MEDICAL file text, masked) and the
text only repeats what they say, in the format the prompts ask for, with its [Sx]
citations. The source fingerprints are saved, so the summaries are not shown as
outdated until a source changes. One VALIDATED per (patient, scope, report).

Per patient, from the `summary` state of scripts.seed_clinical_data: VALIDATED or
SUPERSEDED (an older validated one + the current one) give a timeline summary and a
summary of the last finalized report; DRAFT and REJECTED give a timeline summary in
that state; None leaves the patient without summary, to try the generation.
"""

import json
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timedelta

from beanie.operators import Eq

from app.core.time import utcnow
from app.modules.auth.models import User
from app.modules.llm.models import LlmModule
from app.modules.patient_history.context import Source, SourceKind, collect_sources, patient_profile
from app.modules.patient_history.models import HistoryScope, PatientHistorySummary
from app.modules.patient_history.prompts import (
    NOT_FOUND_ANSWER,
    PROMPT_VERSION,
    REPORT_PROMPT,
    TIMELINE_PROMPT,
    chat_messages,
    summary_messages,
)
from app.modules.patients.dates import CLINIC_TZ
from app.modules.patients.models import Patient, SummaryStatus
from app.modules.reports.models import MedicalReport, ReportStatus

MODEL = "gemini/gemini-3.8-flash"
TITLE = re.compile(r"« (.+?) »")
CONCLUSION = re.compile(r"(?:Conclusion|Commentaire) : (.+?)(?:Document de démonstration|$)", re.S)
FOLLOW_UP = re.compile(r"indiqu|recommand|à prévoir|à rechercher|au-dessus|carence|élevé")
QUESTIONS = (
    "Quel est le dernier résultat d'examen du patient ?",
    "Le patient a-t-il une allergie médicamenteuse connue ?",
)
# (callback of ModuleSeeder._log)
Log = Callable[..., Awaitable[None]]


def _sentence(text: str, limit: int = 180) -> str:
    """First sentence of `text`, on one line, at most `limit` characters."""
    text = " ".join(text.split())
    first = re.split(r"(?<=\.)\s", text, maxsplit=1)[0]
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first


def _sections(text: str) -> dict[str, str]:
    """Sections of a structured report (« ## Titre »), see reports.service.render."""
    chunks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    return {
        title.strip(): body.strip()
        for title, _, body in (chunk.partition("\n") for chunk in chunks)
    }


def _title(source: Source) -> str:
    found = TITLE.search(source.label)
    return found.group(1) if found else source.label


def _fact(source: Source) -> str:
    title = _title(source)
    if source.kind == SourceKind.REPORT:
        sections = _sections(source.text)
        if "Conclusion" in sections:
            return f"consultation « {title} » : {_sentence(sections['Conclusion'])}"
        notes = source.text.partition(":\n")[2] or source.text
        return f"consultation « {title} » (brouillon) : {_sentence(notes)}"
    found = CONCLUSION.search(source.text)
    return f"{title} : {_sentence(found.group(1))}" if found else title


def _day(source: Source) -> str:
    return source.date.astimezone(CLINIC_TZ).date().isoformat() if source.date else "date inconnue"


def timeline_text(sources: list[Source]) -> str:
    events = [f"- {_day(s)} : {_fact(s)} [{s.id}]" for s in sources]
    watch = []
    for source in sources:
        if source.kind == SourceKind.REPORT and "## " not in source.text:
            watch.append(f"- Compte rendu « {_title(source)} » encore à structurer [{source.id}]")
    plans = [s for s in sources if s.kind == SourceKind.REPORT and "Conduite à tenir" in s.text]
    if plans:
        plan = _sections(plans[-1].text)["Conduite à tenir"]
        watch.append(f"- Suivi prévu : {_sentence(plan)} [{plans[-1].id}]")
    for source in reversed(sources):
        found = CONCLUSION.search(source.text) if source.kind == SourceKind.FILE else None
        if found and FOLLOW_UP.search(found.group(1)):
            watch.append(f"- {_title(source)} : {_sentence(found.group(1))} [{source.id}]")
    watch = watch[:5] or ["- Aucun point signalé dans les sources"]
    return "Chronologie\n" + "\n".join(events) + "\nPoints de vigilance\n" + "\n".join(watch)


def report_text(source: Source) -> str:
    sections = _sections(source.text)
    cite = f"[{source.id}]"
    return "\n".join(
        [
            "Motif",
            f"- {_sentence(sections['Motif de consultation'])} {cite}",
            "Constatations",
            f"- {_sentence(sections['Examen clinique'], 300)} {cite}",
            "Conclusion et suite",
            f"- {_sentence(sections['Conclusion'], 300)} {cite}",
            f"- {_sentence(sections['Conduite à tenir'], 300)} {cite}",
        ]
    )


def _chat_answer(question: str, sources: list[Source]) -> dict:
    if "allergie" in question:
        for source in sources:
            for sentence in re.split(r"(?<=\.)\s", " ".join(source.text.split())):
                if "allergi" in sentence.lower():
                    answer = f"{sentence} [{source.id}]"
                    return {"found": True, "answer": answer, "sources": [source.id]}
        return {"found": False, "answer": NOT_FOUND_ANSWER, "sources": []}
    files = [s for s in sources if s.kind == SourceKind.FILE]
    if not files:
        return {"found": False, "answer": NOT_FOUND_ANSWER, "sources": []}
    last = files[-1]
    answer = f"Le {_day(last)}, {_fact(last)} [{last.id}]"
    return {"found": True, "answer": answer, "sources": [last.id]}


class HistorySeeder:
    def __init__(self, log: Log, created: Counter, existing: Counter) -> None:
        self.log = log
        self.created = created
        self.existing = existing

    async def _insert(
        self,
        patient: Patient,
        doctor: User,
        scope: HistoryScope,
        sources: list[Source],
        status: SummaryStatus,
        *,
        report: MedicalReport | None = None,
        comment: str | None = None,
    ) -> None:
        assert patient.id is not None
        if scope == HistoryScope.REPORT:
            content, prompt = report_text(sources[0]), REPORT_PROMPT
        else:
            content, prompt = timeline_text(sources), TIMELINE_PROMPT
        latest = max((s.date for s in sources if s.date), default=utcnow() - timedelta(days=30))
        at = min(latest + timedelta(hours=2), utcnow())
        reviewed = status != SummaryStatus.DRAFT
        summary = await PatientHistorySummary(
            patient_id=patient.id,
            scope=scope,
            report_id=report.id if report else None,
            content=content,
            status=status,
            llm_model=MODEL,
            source_snapshot={
                "promptVersion": PROMPT_VERSION,
                "condensed": False,
                "sources": [source.fingerprint for source in sources],
            },
            generated_by=doctor.id,
            reviewed_by=doctor.id if reviewed else None,
            reviewed_at=min(at + timedelta(hours=3), utcnow()) if reviewed else None,
            review_comment=comment,
        ).insert()
        await summary.set({"createdAt": at})
        self.created["patient_history_summaries"] += 1
        await self.log(
            LlmModule.PATIENT_HISTORY,
            summary_messages(prompt, sources, patient_profile(patient), None),
            at=at - timedelta(minutes=1),
            user_id=doctor.id,
            entity_id=patient.id,
            response=content,
        )

    async def seed(
        self,
        patient: Patient,
        state: str | None,
        reports: list[MedicalReport],
        doctor: User,
    ) -> None:
        if state is None:
            return
        found = await PatientHistorySummary.find_one(
            Eq(PatientHistorySummary.patient_id, patient.id)
        )
        if found is not None:
            self.existing["patient_history_summaries"] += 1
            return
        sources = await collect_sources(patient)
        if not sources:
            return
        timeline = HistoryScope.TIMELINE
        if state == "SUPERSEDED":
            cutoff = utcnow() - timedelta(days=100)
            older = [s for s in sources if s.date and s.date < cutoff]
            older = [replace(s, id=f"S{n}") for n, s in enumerate(older, start=1)]
            if older:
                await self._insert(patient, doctor, timeline, older, SummaryStatus.SUPERSEDED)
        status = {
            "VALIDATED": SummaryStatus.VALIDATED,
            "SUPERSEDED": SummaryStatus.VALIDATED,
            "DRAFT": SummaryStatus.DRAFT,
            "REJECTED": SummaryStatus.REJECTED,
        }[state]
        comment = (
            "Chronologie incomplète : le dernier compte rendu doit être finalisé avant."
            if status == SummaryStatus.REJECTED
            else None
        )
        await self._insert(patient, doctor, timeline, sources, status, comment=comment)
        if status != SummaryStatus.VALIDATED:
            return

        finals = [r for r in reports if r.status == ReportStatus.FINAL and r.structured_content]
        if finals:
            report = finals[-1]
            single = await collect_sources(patient, report_id=report.id)
            await self._insert(
                patient,
                doctor,
                HistoryScope.REPORT,
                single,
                SummaryStatus.VALIDATED,
                report=report,
            )
        await self._chat(patient, doctor)

    async def _chat(self, patient: Patient, doctor: User) -> None:
        sources = await collect_sources(patient, include_notes=True)
        asked: datetime = utcnow() - timedelta(days=1, hours=2)
        for question in QUESTIONS:
            answer = _chat_answer(question, sources)
            await self.log(
                LlmModule.PATIENT_CHAT,
                chat_messages(question, [], sources, patient_profile(patient)),
                at=asked,
                user_id=doctor.id,
                entity_id=patient.id,
                response=json.dumps(answer, ensure_ascii=False),
            )
            asked += timedelta(minutes=3)
