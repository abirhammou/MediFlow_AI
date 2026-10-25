from datetime import date
from typing import Any

from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from pymongo.errors import DuplicateKeyError

from app.core.sequence import next_record_number
from app.core.time import utcnow
from app.errors import APIError
from app.modules.auth.models import User
from app.modules.patients import repository
from app.modules.patients.dates import age_on, clinic_today, from_mongo_date, to_mongo_date
from app.modules.patients.models import BloodType, Gender, Patient
from app.modules.patients.repository import PatientListView
from app.modules.patients.schemas import (
    DeletedPatientItem,
    Page,
    PatientCreate,
    PatientListItem,
    PatientOut,
    PatientUpdate,
)

NATIONAL_ID_INDEX = "uq_patients_national_id"


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Dossier patient introuvable."
    )


def _object_id(patient_id: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(patient_id)
    except (InvalidId, TypeError):
        raise _not_found() from None


def _duplicate_national_id(exc: DuplicateKeyError) -> APIError:
    if NATIONAL_ID_INDEX not in str(exc):
        raise exc
    return APIError(409, "national_id_exists", "Un patient avec ce CIN existe déjà")


def _list_item(view: PatientListView) -> PatientListItem:
    birth_date = from_mongo_date(view.date_of_birth)
    return PatientListItem(
        id=str(view.id),
        record_number=view.record_number,
        first_name=view.first_name,
        last_name=view.last_name,
        date_of_birth=birth_date,
        age=age_on(birth_date, clinic_today()),
        gender=view.gender,
        phone=view.phone,
        city=view.city,
    )


def _deleted_item(view: PatientListView) -> DeletedPatientItem:
    assert view.deleted_at is not None
    return DeletedPatientItem(**_list_item(view).model_dump(), deleted_at=view.deleted_at)


def _mongo_changes(data: PatientUpdate) -> dict[str, Any]:
    """`$set` document for the fields sent, with the MongoDB (camelCase) names."""
    changes: dict[str, Any] = {}
    for name in data.model_fields_set:
        value = getattr(data, name)
        if isinstance(value, BaseModel):
            value = value.model_dump(by_alias=True)  # nested objects are replaced as a whole
        elif isinstance(value, date):
            value = to_mongo_date(value)
        changes[to_camel(name)] = value
    return changes


class PatientService:
    async def create_patient(self, data: PatientCreate, user: User) -> PatientOut:
        patient = Patient(
            **data.model_dump(),
            record_number=await next_record_number(),
            created_by=user.id,
            updated_by=user.id,
        )
        try:
            await patient.insert()
        except DuplicateKeyError as exc:
            raise _duplicate_national_id(exc) from None
        return PatientOut.from_patient(patient)

    async def get_patient(self, patient_id: str) -> PatientOut:
        patient = await repository.get_patient(_object_id(patient_id))
        if patient is None:
            raise _not_found()
        return PatientOut.from_patient(patient)

    async def list_patients(
        self,
        *,
        q: str | None,
        gender: Gender | None,
        blood_type: BloodType | None,
        city: str | None,
        page: int,
        size: int,
        sort: str | None,
    ) -> Page[PatientListItem]:
        result = await repository.list_patients(
            page, size, q, gender=gender, blood_type=blood_type, city=city, sort=sort
        )
        return Page(
            items=[_list_item(view) for view in result.items],
            total=result.total,
            page=page,
            size=size,
        )

    async def list_deleted(self, *, page: int, size: int) -> Page[DeletedPatientItem]:
        result = await repository.list_patients(page, size, deleted=True)
        return Page(
            items=[_deleted_item(view) for view in result.items],
            total=result.total,
            page=page,
            size=size,
        )

    async def update_patient(self, patient_id: str, data: PatientUpdate, user: User) -> PatientOut:
        changes = _mongo_changes(data) | {"updatedBy": user.id, "updatedAt": utcnow()}
        try:
            patient = await repository.update_patient_fields(_object_id(patient_id), changes)
        except DuplicateKeyError as exc:
            raise _duplicate_national_id(exc) from None
        if patient is None:
            raise _not_found()
        return PatientOut.from_patient(patient)

    async def soft_delete_patient(self, patient_id: str, user: User) -> None:
        now = utcnow()
        changes = {"deletedAt": now, "updatedBy": user.id, "updatedAt": now}
        if await repository.update_patient_fields(_object_id(patient_id), changes) is None:
            raise _not_found()

    async def restore_patient(self, patient_id: str, user: User) -> PatientOut:
        changes = {"deletedAt": None, "updatedBy": user.id, "updatedAt": utcnow()}
        patient = await repository.update_patient_fields(
            _object_id(patient_id), changes, deleted=True
        )
        if patient is None:
            raise _not_found()
        return PatientOut.from_patient(patient)

    async def find_possible_duplicates(
        self, first_name: str, last_name: str, date_of_birth: date
    ) -> list[PatientListItem]:
        views = await repository.find_duplicates(
            first_name.strip(), last_name.strip(), to_mongo_date(date_of_birth)
        )
        return [_list_item(view) for view in views]
