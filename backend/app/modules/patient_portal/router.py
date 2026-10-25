"""Patient accounts (/api/patients/{id}/account) and the patient's own portal (/api/portal)."""

from fastapi import APIRouter, Depends, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.patient_portal.schemas import (
    AccountCreate,
    AccountCredentials,
    AccountOut,
    PortalFollowUp,
    PortalProfile,
)
from app.modules.patient_portal.service import PatientAccountService, PortalService

router = APIRouter()
PREFIX = "/api"
TAGS = ["patient-portal"]
LLM_ENABLED = False

# Who may do what (the frontend mirrors it in patient-permissions.ts).
PORTAL_ROLES: dict[str, tuple[Role, ...]] = {
    "accounts": (Role.SECRETARY, Role.ADMIN),
    "portal": (Role.PATIENT,),
}
account_managers = require_roles(*PORTAL_ROLES["accounts"])
patients_only = require_roles(*PORTAL_ROLES["portal"])


def get_account_service() -> PatientAccountService:
    return PatientAccountService()


def get_portal_service() -> PortalService:
    return PortalService()


@router.get("/patients/{patient_id}/account", response_model=AccountOut)
async def get_account(
    patient_id: str,
    _: User = Depends(account_managers),
    service: PatientAccountService = Depends(get_account_service),
) -> AccountOut:
    return await service.get(patient_id)


@router.post(
    "/patients/{patient_id}/account",
    response_model=AccountCredentials,
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    patient_id: str,
    data: AccountCreate,
    user: User = Depends(account_managers),
    service: PatientAccountService = Depends(get_account_service),
) -> AccountCredentials:
    """Active PATIENT login linked to the record; the temporary password is shown once."""
    return await service.create(user, patient_id, data)


@router.post("/patients/{patient_id}/account/reset-password", response_model=AccountCredentials)
async def reset_password(
    patient_id: str,
    user: User = Depends(account_managers),
    service: PatientAccountService = Depends(get_account_service),
) -> AccountCredentials:
    return await service.reset_password(user, patient_id)


@router.get("/portal/me", response_model=PortalProfile)
async def my_record(
    user: User = Depends(patients_only),
    service: PortalService = Depends(get_portal_service),
) -> PortalProfile:
    return await service.profile(user)


@router.get("/portal/follow-ups", response_model=list[PortalFollowUp])
async def my_follow_ups(
    user: User = Depends(patients_only),
    service: PortalService = Depends(get_portal_service),
) -> list[PortalFollowUp]:
    return await service.follow_ups(user)
