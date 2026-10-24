import re

from beanie import PydanticObjectId
from beanie.operators import Eq, Text

from app.core.models import AiReviewStatus
from app.core.pagination import Page, check_page
from app.modules.patients.models import RECORD_NUMBER_PATTERN, Patient, PatientSummary

_RECORD_NUMBER = re.compile(RECORD_NUMBER_PATTERN, re.IGNORECASE)


def _not_deleted() -> Eq:
    # Matches deletedAt: null and a missing deletedAt.
    return Eq(Patient.deleted_at, None)


async def list_patients(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> Page[Patient]:
    """Non-deleted patients sorted by name.

    `search` is a full record number (exact match) or words matched by the
    French text index on first name, last name and record number (whole words,
    stemmed: "Ben" does not match "Benali").
    """
    skip = check_page(page, page_size)
    filters = [_not_deleted()]
    term = (search or "").strip()
    if _RECORD_NUMBER.fullmatch(term):
        filters.append(Eq(Patient.record_number, term.upper()))
    elif term:
        filters.append(Text(term))

    query = Patient.find(*filters)
    total = await query.count()
    items = (
        await query.sort(+Patient.last_name, +Patient.first_name, +Patient.id)
        .skip(skip)
        .limit(page_size)
        .to_list()
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


async def get_patient(patient_id: PydanticObjectId) -> Patient | None:
    return await Patient.find_one(Eq(Patient.id, patient_id), _not_deleted())


async def get_latest_summary(patient_id: PydanticObjectId) -> PatientSummary | None:
    return (
        await PatientSummary.find(Eq(PatientSummary.patient_id, patient_id))
        .sort(-PatientSummary.created_at, -PatientSummary.id)
        .first_or_none()
    )


async def get_validated_summary(patient_id: PydanticObjectId) -> PatientSummary | None:
    return await PatientSummary.find_one(
        Eq(PatientSummary.patient_id, patient_id),
        Eq(PatientSummary.status, AiReviewStatus.VALIDATED),
    )
