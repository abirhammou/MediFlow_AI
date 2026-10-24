from enum import Enum
from typing import Self

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field, model_validator

from app.core.models import CamelModel, CreatedAtDocument, TimestampedDocument


class AppointmentStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class DayPart(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"


class Appointment(TimestampedDocument):
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId = Field(description="users._id with role DOCTOR")
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=255)
    status: AppointmentStatus = AppointmentStatus.PENDING
    cancel_reason: str | None = None
    created_by: PydanticObjectId | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self

    class Settings:
        name = "appointments"


class ParsedRequest(CamelModel):
    """Structured LLM output extracted from a free-text appointment request."""

    preferred_date: AwareDatetime | None = None
    day_part: DayPart | None = None
    doctor_id: PydanticObjectId | None = None
    specialty: str | None = None
    reason: str | None = None


class AppointmentRequest(CreatedAtDocument):
    raw_message: str = Field(max_length=2000)
    parsed: ParsedRequest | None = None
    patient_id: PydanticObjectId | None = None
    appointment_id: PydanticObjectId | None = None
    created_by: PydanticObjectId | None = None

    class Settings:
        name = "appointment_requests"
