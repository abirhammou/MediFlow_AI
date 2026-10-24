from datetime import date, datetime
from enum import Enum
from typing import Any

from beanie import Insert, PydanticObjectId, Replace, Save, before_event
from pydantic import AwareDatetime, Field, field_validator

from app.core.models import (
    AiReviewStatus,
    CamelModel,
    CreatedAtDocument,
    TimestampedDocument,
    normalize_email,
)
from app.core.time import utc_midnight

RECORD_NUMBER_PATTERN = r"^PAT-[0-9]{4}-[0-9]{5}$"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class BloodType(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"


class Address(CamelModel):
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None


class Insurance(CamelModel):
    provider: str | None = None
    number: str | None = None


class EmergencyContact(CamelModel):
    name: str | None = None
    phone: str | None = None
    relation: str | None = None


class Patient(TimestampedDocument):
    record_number: str = Field(pattern=RECORD_NUMBER_PATTERN)
    first_name: str = Field(max_length=80)
    last_name: str = Field(max_length=80)
    date_of_birth: AwareDatetime = Field(description="midnight UTC; use `birth_date` for the date")
    gender: Gender
    national_id: str | None = Field(default=None, max_length=30, description="fictitious CIN")
    phone: str | None = None
    email: str | None = None
    address: Address | None = None
    blood_type: BloodType | None = None
    insurance: Insurance | None = None
    emergency_contact: EmergencyContact | None = None
    administrative_notes: str | None = Field(default=None, max_length=5000)
    current_summary_id: PydanticObjectId | None = Field(
        default=None, description="the VALIDATED patient_summaries document"
    )
    created_by: PydanticObjectId | None = None
    updated_by: PydanticObjectId | None = None
    deleted_at: AwareDatetime | None = Field(default=None, description="soft delete")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _date_to_utc_midnight(cls, value: Any) -> Any:
        if isinstance(value, date) and not isinstance(value, datetime):
            return utc_midnight(value)
        return value

    @property
    def birth_date(self) -> date:
        return self.date_of_birth.date()

    @before_event(Insert, Replace, Save)
    def _normalize_email(self) -> None:
        if self.email is not None:
            self.email = normalize_email(self.email)

    class Settings:
        name = "patients"


class PatientSummary(CreatedAtDocument):
    """Every AI draft is kept; at most one VALIDATED summary per patient (unique index)."""

    patient_id: PydanticObjectId
    content: str = Field(min_length=1, max_length=4000)
    status: AiReviewStatus = AiReviewStatus.DRAFT
    llm_model: str | None = None
    source_snapshot: dict[str, Any] | None = Field(
        default=None, description="patient fields sent to the LLM"
    )
    generated_by: PydanticObjectId | None = None
    reviewed_by: PydanticObjectId | None = None
    reviewed_at: AwareDatetime | None = None
    review_comment: str | None = None

    class Settings:
        name = "patient_summaries"
