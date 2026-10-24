"""AI administrative summary of a patient record: generate, edit, validate, reject.

Only the fields listed in `build_source_snapshot` leave the server (data
minimization); the snapshot is saved with the summary, so we know exactly what
the model received.
"""

import re
from datetime import timedelta
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import In
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.time import utcnow
from app.errors import APIError, LLMResponseError
from app.llm.anonymizer import anonymize
from app.llm.client import complete
from app.llm.interactions import count_interactions
from app.modules.auth.models import User
from app.modules.llm.models import LlmModule
from app.modules.patients import repository
from app.modules.patients.dates import age_on, clinic_today, from_mongo_date
from app.modules.patients.models import (
    SUMMARY_MAX_LENGTH,
    Gender,
    Patient,
    PatientSummary,
    SummaryStatus,
)
from app.modules.patients.summary_prompt import PROMPT_VERSION, build_messages
from app.modules.patients.summary_schemas import SummaryOut, SummaryReject, SummaryUpdate

LLM_MODULE = LlmModule.PATIENT_RECORD
GENERATIONS_PER_HOUR = 10
GENDER_LABELS = {Gender.MALE: "Homme", Gender.FEMALE: "Femme", Gender.OTHER: "Autre"}
# A line that is only a Markdown code fence (``` or ```text).
CODE_FENCE = re.compile(r"^[ \t]*```[\w-]*[ \t]*$\n?", re.MULTILINE)
PATIENT_NOT_FOUND = "Dossier patient introuvable."
SUMMARY_NOT_FOUND = "Résumé introuvable."


def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _object_id(value: str, not_found: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError):
        raise _error(status.HTTP_404_NOT_FOUND, not_found) from None


def build_source_snapshot(patient: Patient) -> dict[str, Any]:
    """What the model may see: no name, birth date, CIN, phone, email, street,
    insurance number or emergency contact details. Contact details typed in the
    notes are masked."""
    contact = patient.emergency_contact
    notes = (patient.administrative_notes or "").strip()
    return {
        "recordNumber": patient.record_number,
        "age": age_on(from_mongo_date(patient.date_of_birth), clinic_today()),
        "gender": GENDER_LABELS[patient.gender],
        "bloodType": patient.blood_type.value if patient.blood_type else None,
        "city": patient.address.city if patient.address else None,
        "insuranceProvider": patient.insurance.provider if patient.insurance else None,
        "hasEmergencyContact": bool(contact and (contact.name or contact.phone)),
        "administrativeNotes": anonymize(notes) if notes else None,
    }


def clean_summary(text: str) -> str:
    """Strip code fences and whitespace; an empty or too long text is a 502 (never truncated)."""
    text = CODE_FENCE.sub("", text).strip()
    if not text:
        raise LLMResponseError()
    if len(text) > SUMMARY_MAX_LENGTH:
        raise APIError(
            502,
            "summary_too_long",
            f"Le résumé généré dépasse {SUMMARY_MAX_LENGTH} caractères. Relancez la génération.",
        )
    return text


def is_outdated(summary: PatientSummary, current: dict[str, Any]) -> bool:
    """The record changed since generation (a summary without snapshot counts as outdated)."""
    snapshot = summary.source_snapshot or {}
    return snapshot.get("patient") != current


async def _names(user_ids: set[PydanticObjectId]) -> dict[PydanticObjectId, str]:
    if not user_ids:
        return {}
    users = await User.find(In(User.id, list(user_ids))).to_list()
    return {user.id: f"{user.first_name} {user.last_name}" for user in users if user.id}


def _str_or_none(value: object | None) -> str | None:
    return None if value is None else str(value)


class SummaryService:
    async def _patient(self, patient_id: str) -> Patient:
        """Non-deleted patient, else 404 (also for soft-deleted records)."""
        patient = await repository.get_patient(_object_id(patient_id, PATIENT_NOT_FOUND))
        if patient is None:
            raise _error(status.HTTP_404_NOT_FOUND, PATIENT_NOT_FOUND)
        return patient

    async def _summary(self, patient: Patient, summary_id: str) -> PatientSummary:
        assert patient.id is not None
        summary = await repository.get_summary(
            patient.id, _object_id(summary_id, SUMMARY_NOT_FOUND)
        )
        if summary is None:
            raise _error(status.HTTP_404_NOT_FOUND, SUMMARY_NOT_FOUND)
        return summary

    async def _out(self, patient: Patient, summaries: list[PatientSummary]) -> list[SummaryOut]:
        current = build_source_snapshot(patient)
        names = await _names(
            {
                user_id
                for summary in summaries
                for user_id in (summary.generated_by, summary.reviewed_by)
                if user_id is not None
            }
        )
        result = []
        for summary in summaries:
            snapshot = summary.source_snapshot or {}
            result.append(
                SummaryOut(
                    id=str(summary.id),
                    patient_id=str(summary.patient_id),
                    content=summary.content,
                    status=summary.status,
                    llm_model=summary.llm_model,
                    prompt_version=snapshot.get("promptVersion"),
                    source_snapshot=snapshot.get("patient"),
                    is_outdated=is_outdated(summary, current),
                    generated_by=_str_or_none(summary.generated_by),
                    generated_by_name=names.get(summary.generated_by),
                    reviewed_by=_str_or_none(summary.reviewed_by),
                    reviewed_by_name=names.get(summary.reviewed_by),
                    reviewed_at=summary.reviewed_at,
                    review_comment=summary.review_comment,
                    created_at=summary.created_at,
                )
            )
        return result

    async def _one(self, patient: Patient, summary: PatientSummary) -> SummaryOut:
        return (await self._out(patient, [summary]))[0]

    async def generate(self, patient_id: str, user: User) -> SummaryOut:
        patient = await self._patient(patient_id)
        assert user.id is not None
        since = utcnow() - timedelta(hours=1)
        if await count_interactions(LLM_MODULE, user.id, since) >= GENERATIONS_PER_HOUR:
            raise APIError(
                429,
                "summary_rate_limited",
                f"Limite atteinte : {GENERATIONS_PER_HOUR} générations de résumé par heure. "
                "Réessayez plus tard.",
            )

        data = build_source_snapshot(patient)
        result = await complete(
            module=LLM_MODULE,
            messages=build_messages(data),
            entity_id=patient.id,
            user_id=user.id,
            postprocess=clean_summary,
        )
        summary = PatientSummary(
            patient_id=patient.id,
            content=result.text,
            status=SummaryStatus.DRAFT,
            llm_model=result.model,
            source_snapshot={"promptVersion": PROMPT_VERSION, "patient": data},
            generated_by=user.id,
        )
        await summary.insert()
        return await self._one(patient, summary)

    async def list_summaries(self, patient_id: str) -> list[SummaryOut]:
        patient = await self._patient(patient_id)
        assert patient.id is not None
        return await self._out(patient, await repository.list_summaries(patient.id))

    async def current(self, patient_id: str) -> SummaryOut:
        patient = await self._patient(patient_id)
        assert patient.id is not None
        summary = await repository.get_validated_summary(patient.id)
        if summary is None:
            raise _error(status.HTTP_404_NOT_FOUND, "Aucun résumé validé pour ce patient.")
        return await self._one(patient, summary)

    async def _change_draft(
        self, summary: PatientSummary, changes: dict[str, Any], action: str
    ) -> PatientSummary:
        """Apply `changes` only while the summary is a DRAFT, else 409."""
        assert summary.id is not None
        if summary.status == SummaryStatus.DRAFT:
            updated = await repository.update_summary(summary.id, [SummaryStatus.DRAFT], changes)
            if updated is not None:
                return updated
        raise _error(status.HTTP_409_CONFLICT, f"Seul un brouillon peut être {action}.")

    async def update_content(
        self, patient_id: str, summary_id: str, data: SummaryUpdate
    ) -> SummaryOut:
        patient = await self._patient(patient_id)
        summary = await self._summary(patient, summary_id)
        updated = await self._change_draft(summary, {"content": data.content}, "modifié")
        return await self._one(patient, updated)

    async def reject(
        self, patient_id: str, summary_id: str, data: SummaryReject, user: User
    ) -> SummaryOut:
        patient = await self._patient(patient_id)
        summary = await self._summary(patient, summary_id)
        changes = {
            "status": SummaryStatus.REJECTED,
            "reviewedBy": user.id,
            "reviewedAt": utcnow(),
            "reviewComment": data.comment,
        }
        updated = await self._change_draft(summary, changes, "rejeté")
        return await self._one(patient, updated)

    async def validate(self, patient_id: str, summary_id: str, user: User) -> SummaryOut:
        """Three idempotent steps (no transaction: MongoDB is standalone).

        1. the previous VALIDATED summary becomes SUPERSEDED;
        2. this DRAFT becomes VALIDATED (the unique index refuses a second one: 409);
        3. `patients.currentSummaryId` points to the VALIDATED summary.
        Validating an already VALIDATED summary again replays steps 1 and 3, so a
        retry repairs a validation interrupted half-way.
        """
        patient = await self._patient(patient_id)
        summary = await self._summary(patient, summary_id)
        assert patient.id is not None and summary.id is not None
        if summary.status not in (SummaryStatus.DRAFT, SummaryStatus.VALIDATED):
            raise _error(status.HTTP_409_CONFLICT, "Seul un brouillon peut être validé.")

        await repository.supersede_validated(patient.id, keep=summary.id)
        if summary.status == SummaryStatus.DRAFT:
            changes = {
                "status": SummaryStatus.VALIDATED,
                "reviewedBy": user.id,
                "reviewedAt": utcnow(),
            }
            try:
                updated = await repository.update_summary(
                    summary.id, [SummaryStatus.DRAFT], changes
                )
            except DuplicateKeyError:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "Un autre résumé vient d'être validé pour ce patient. Rechargez la page.",
                ) from None
            if updated is None:
                raise _error(status.HTTP_409_CONFLICT, "Seul un brouillon peut être validé.")
            summary = updated

        # Points to whatever is VALIDATED now (a concurrent validation may have won).
        # Not a change of the record itself: updatedAt / updatedBy stay as they are.
        validated = await repository.get_validated_summary(patient.id)
        current_id = validated.id if validated else None
        if patient.current_summary_id != current_id:
            await repository.update_patient_fields(patient.id, {"currentSummaryId": current_id})
        return await self._one(patient, summary)
