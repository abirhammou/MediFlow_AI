from datetime import date

from beanie import PydanticObjectId
from pydantic import AwareDatetime, BaseModel, Field

from app.modules.appointments.models import AppointmentStatus, DayPart

# ── CRUD ──────────────────────────────────────────────────────────────────────


class AppointmentCreate(BaseModel):
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId
    start_at: AwareDatetime
    end_at: AwareDatetime | None = Field(
        default=None, description="Par défaut : 30 minutes après le début."
    )
    reason: str | None = Field(default=None, max_length=255)
    request_id: PydanticObjectId | None = Field(
        default=None, description="Demande en langage libre dont ce rendez-vous est issu."
    )


class AppointmentUpdate(BaseModel):
    doctor_id: PydanticObjectId | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    reason: str | None = Field(default=None, max_length=255)
    status: AppointmentStatus | None = None


class AppointmentCancel(BaseModel):
    cancel_reason: str | None = Field(default=None, max_length=255)


class AppointmentOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str | None
    status: AppointmentStatus
    cancel_reason: str | None


# ── LLM ───────────────────────────────────────────────────────────────────────


class AppointmentIntent(BaseModel):
    """Sortie du LLM : ce que le patient demande, rien de plus."""

    preferred_date: date | None = Field(default=None, description="YYYY-MM-DD, null si absente")
    day_part: DayPart | None = None
    specialty: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=255)


class ParseRequestIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    patient_id: PydanticObjectId | None = Field(
        default=None, description="Ignoré pour un patient : son propre dossier est utilisé."
    )
    doctor_id: PydanticObjectId | None = Field(
        default=None, description="Si absent, tous les médecins actifs (de la spécialité) sont proposés."
    )


class SlotOut(BaseModel):
    doctor_id: str
    doctor_name: str
    start_at: AwareDatetime
    end_at: AwareDatetime


class ParseRequestOut(BaseModel):
    request_id: str
    parsed: AppointmentIntent
    available_slots: list[SlotOut]
