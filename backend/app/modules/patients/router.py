from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.pagination import MAX_PAGE_SIZE
from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.patients.models import BloodType, Gender
from app.modules.patients.repository import SORT_PATTERN
from app.modules.patients.schemas import (
    DeletedPatientItem,
    Page,
    PatientCreate,
    PatientListItem,
    PatientOut,
    PatientUpdate,
)
from app.modules.patients.service import PatientService

router = APIRouter()
TAGS = ["patients"]
LLM_ENABLED = False

# Who may do what on patient records (the frontend mirrors it to hide buttons).
PATIENT_ROLES: dict[str, tuple[Role, ...]] = {
    "read": (Role.SECRETARY, Role.DOCTOR, Role.ADMIN),
    "write": (Role.SECRETARY, Role.ADMIN),
    "restore": (Role.ADMIN,),
}
readers = require_roles(*PATIENT_ROLES["read"])
writers = require_roles(*PATIENT_ROLES["write"])
restorers = require_roles(*PATIENT_ROLES["restore"])


def get_patient_service() -> PatientService:
    return PatientService()


@router.get("", response_model=Page[PatientListItem])
async def list_patients(
    q: str | None = Query(default=None, max_length=100),
    gender: Gender | None = None,
    blood_type: BloodType | None = Query(default=None, alias="bloodType"),
    city: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    sort: str | None = Query(default=None, pattern=SORT_PATTERN),
    _: User = Depends(readers),
    service: PatientService = Depends(get_patient_service),
) -> Page[PatientListItem]:
    """`sort`: lastName, createdAt, recordNumber or dateOfBirth; prefix with `-` for descending."""
    return await service.list_patients(
        q=q, gender=gender, blood_type=blood_type, city=city, page=page, size=size, sort=sort
    )


@router.get("/duplicates", response_model=list[PatientListItem])
async def find_duplicates(
    first_name: str = Query(alias="firstName", min_length=1, max_length=80),
    last_name: str = Query(alias="lastName", min_length=1, max_length=80),
    date_of_birth: date = Query(alias="dateOfBirth"),
    _: User = Depends(writers),
    service: PatientService = Depends(get_patient_service),
) -> list[PatientListItem]:
    """Possible duplicates: same first and last name (case-insensitive) and birth date."""
    return await service.find_possible_duplicates(first_name, last_name, date_of_birth)


@router.get("/deleted", response_model=Page[DeletedPatientItem])
async def list_deleted_patients(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    _: User = Depends(restorers),
    service: PatientService = Depends(get_patient_service),
) -> Page[DeletedPatientItem]:
    return await service.list_deleted(page=page, size=size)


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: str,
    _: User = Depends(readers),
    service: PatientService = Depends(get_patient_service),
) -> PatientOut:
    return await service.get_patient(patient_id)


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreate,
    user: User = Depends(writers),
    service: PatientService = Depends(get_patient_service),
) -> PatientOut:
    return await service.create_patient(data, user)


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: str,
    data: PatientUpdate,
    user: User = Depends(writers),
    service: PatientService = Depends(get_patient_service),
) -> PatientOut:
    return await service.update_patient(patient_id, data, user)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: str,
    user: User = Depends(writers),
    service: PatientService = Depends(get_patient_service),
) -> Response:
    """Soft delete: the record is hidden (deletedAt), never removed."""
    await service.soft_delete_patient(patient_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{patient_id}/restore", response_model=PatientOut)
async def restore_patient(
    patient_id: str,
    user: User = Depends(restorers),
    service: PatientService = Depends(get_patient_service),
) -> PatientOut:
    return await service.restore_patient(patient_id, user)
