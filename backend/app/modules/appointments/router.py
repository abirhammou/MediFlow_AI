from datetime import datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import MAX_PAGE_SIZE, Page
from app.dependencies import require_roles
from app.modules.appointments.models import AppointmentStatus
from app.modules.appointments.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentOut,
    AppointmentUpdate,
    ParseRequestIn,
    ParseRequestOut,
)
from app.modules.appointments.service import AppointmentService
from app.modules.auth.models import Role, User

router = APIRouter()
PREFIX = "/api/appointments"
TAGS = ["appointments"]

STAFF = (Role.ADMIN, Role.SECRETARY, Role.DOCTOR)
ALL_ROLES = (*STAFF, Role.PATIENT)


def get_service() -> AppointmentService:
    return AppointmentService()


# ── CRUD ──────────────────────────────────────────────────────────────────────


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    user: User = Depends(require_roles(*ALL_ROLES)),
    service: AppointmentService = Depends(get_service),
) -> AppointmentOut:
    """Créer un rendez-vous (un patient ne peut le faire que pour son propre dossier)."""
    return await service.create(data, user)


@router.get("", response_model=Page[AppointmentOut])
async def list_appointments(
    patient_id: PydanticObjectId | None = None,
    doctor_id: PydanticObjectId | None = None,
    status: AppointmentStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = Query(default=None, description="Exclu"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    user: User = Depends(require_roles(*ALL_ROLES)),
    service: AppointmentService = Depends(get_service),
) -> Page[AppointmentOut]:
    """Consulter les rendez-vous (filtrés automatiquement selon le rôle)."""
    return await service.list_appointments(
        user,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


# ── LLM (déclaré avant /{appointment_id} pour que le chemin fixe soit prioritaire) ──


@router.post("/parse-request", response_model=ParseRequestOut)
async def parse_request(
    body: ParseRequestIn,
    user: User = Depends(require_roles(*ALL_ROLES)),
    service: AppointmentService = Depends(get_service),
) -> ParseRequestOut:
    """Message libre -> demande structurée + créneaux réellement disponibles."""
    return await service.parse_request(body, user)


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: PydanticObjectId,
    user: User = Depends(require_roles(*ALL_ROLES)),
    service: AppointmentService = Depends(get_service),
) -> AppointmentOut:
    return await service.get(appointment_id, user)


@router.put("/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: PydanticObjectId,
    changes: AppointmentUpdate,
    user: User = Depends(require_roles(*STAFF)),
    service: AppointmentService = Depends(get_service),
) -> AppointmentOut:
    """Modifier ou déplacer un rendez-vous (personnel de la clinique uniquement)."""
    return await service.update(appointment_id, changes, user)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: PydanticObjectId,
    body: AppointmentCancel | None = None,
    user: User = Depends(require_roles(*ALL_ROLES)),
    service: AppointmentService = Depends(get_service),
) -> AppointmentOut:
    """Annuler un rendez-vous : il reste dans l'historique avec le statut CANCELLED."""
    return await service.cancel(appointment_id, body or AppointmentCancel(), user)
