import re
from datetime import datetime
from typing import Any

from beanie import PydanticObjectId, SortDirection, UpdateResponse
from beanie.operators import NE, And, Eq, Or, RegEx, Set
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.models import AiReviewStatus
from app.core.pagination import Page, check_page
from app.modules.patients.models import BloodType, Gender, Patient, PatientSummary

# API sort keys -> MongoDB fields; "-key" sorts descending.
SORTABLE_FIELDS = {
    "lastName": "lastName",
    "createdAt": "createdAt",
    "recordNumber": "recordNumber",
    "dateOfBirth": "dateOfBirth",
}
SORT_PATTERN = rf"^-?({'|'.join(SORTABLE_FIELDS)})$"
# Field names, not `Patient.last_name`: those only exist once Beanie is initialised.
SEARCH_FIELDS = ("lastName", "firstName", "recordNumber", "nationalId")


class PatientListView(BaseModel):
    """List projection: only what the patients table shows."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: PydanticObjectId = Field(alias="_id")
    record_number: str
    first_name: str
    last_name: str
    date_of_birth: AwareDatetime
    gender: Gender
    phone: str | None = None
    city: str | None = None
    deleted_at: AwareDatetime | None = None

    class Settings:
        projection = {
            "_id": 1,
            "recordNumber": 1,
            "firstName": 1,
            "lastName": 1,
            "dateOfBirth": 1,
            "gender": 1,
            "phone": 1,
            "city": "$address.city",
            "deletedAt": 1,
        }


def _not_deleted() -> Eq:
    # Matches deletedAt: null and a missing deletedAt.
    return Eq(Patient.deleted_at, None)


def _deleted() -> NE:
    return NE(Patient.deleted_at, None)


def _prefix(term: str) -> str:
    return f"^{re.escape(term)}"


def _search_filter(term: str) -> Or:
    """The whole term, or every word of it, starts one of the searched fields.

    Case-insensitive anchored regexes: the French text index only matches whole
    stemmed words ("Ben" would not find "Benali").
    """

    def any_field_starts_with(prefix: str) -> Or:
        return Or(*(RegEx(field, _prefix(prefix), "i") for field in SEARCH_FIELDS))

    words = term.split()
    if len(words) <= 1:
        return any_field_starts_with(term)
    return Or(any_field_starts_with(term), And(*(any_field_starts_with(word) for word in words)))


def _sort(sort: str | None, *, deleted: bool) -> list[tuple[str, SortDirection]]:
    if sort is None:
        keys = [("deletedAt", SortDirection.DESCENDING)] if deleted else []
        keys += [("lastName", SortDirection.ASCENDING), ("firstName", SortDirection.ASCENDING)]
    else:
        direction = SortDirection.DESCENDING if sort.startswith("-") else SortDirection.ASCENDING
        field = SORTABLE_FIELDS[sort.removeprefix("-")]
        keys = [(field, direction)]
        if field == "lastName":
            keys.append(("firstName", direction))
    # _id follows creation order: same direction as the main key, so ties stay stable.
    return [*keys, ("_id", keys[0][1])]


async def list_patients(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    *,
    gender: Gender | None = None,
    blood_type: BloodType | None = None,
    city: str | None = None,
    sort: str | None = None,
    deleted: bool = False,
) -> Page[PatientListView]:
    """Non-deleted patients (or only deleted ones), sorted by name by default.

    `search` matches the start of the last name, first name, record number or
    national ID, case-insensitively. `city` is a case-insensitive exact match.
    """
    skip = check_page(page, page_size)
    filters: list[Any] = [_deleted() if deleted else _not_deleted()]
    term = (search or "").strip()
    if term:
        filters.append(_search_filter(term))
    if gender is not None:
        filters.append(Eq(Patient.gender, gender))
    if blood_type is not None:
        filters.append(Eq(Patient.blood_type, blood_type))
    if city and city.strip():
        filters.append(RegEx("address.city", f"^{re.escape(city.strip())}$", "i"))

    query = Patient.find(*filters)
    total = await query.count()
    items = (
        await query.sort(*_sort(sort, deleted=deleted))
        .skip(skip)
        .limit(page_size)
        .project(PatientListView)
        .to_list()
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


async def get_patient(patient_id: PydanticObjectId) -> Patient | None:
    return await Patient.find_one(Eq(Patient.id, patient_id), _not_deleted())


async def find_duplicates(
    first_name: str, last_name: str, date_of_birth: datetime
) -> list[PatientListView]:
    """Non-deleted patients with the same names (case-insensitive) and birth date."""
    return (
        await Patient.find(
            RegEx(Patient.first_name, f"^{re.escape(first_name)}$", "i"),
            RegEx(Patient.last_name, f"^{re.escape(last_name)}$", "i"),
            Eq(Patient.date_of_birth, date_of_birth),
            _not_deleted(),
        )
        .sort(*_sort(None, deleted=False))
        .project(PatientListView)
        .to_list()
    )


async def update_patient_fields(
    patient_id: PydanticObjectId, changes: dict[str, Any], *, deleted: bool = False
) -> Patient | None:
    """`$set` on a non-deleted patient (or a deleted one); returns the updated document.

    `changes` uses the MongoDB (camelCase) field names. Partial updates bypass
    the Beanie hooks: the caller sets `updatedAt`.
    """
    return await Patient.find_one(
        Eq(Patient.id, patient_id), _deleted() if deleted else _not_deleted()
    ).update(Set(changes), response_type=UpdateResponse.NEW_DOCUMENT)


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
