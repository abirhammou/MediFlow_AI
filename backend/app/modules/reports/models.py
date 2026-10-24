from enum import Enum

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import TimestampedDocument


class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    ARCHIVED = "ARCHIVED"


class MedicalReport(TimestampedDocument):
    patient_id: PydanticObjectId
    doctor_id: PydanticObjectId
    appointment_id: PydanticObjectId | None = None
    title: str = Field(max_length=200)
    raw_notes: str = Field(description="professional's notes = source of truth")
    structured_content: str | None = Field(
        default=None, description="LLM output, no added medical facts"
    )
    status: ReportStatus = ReportStatus.DRAFT
    archived_at: AwareDatetime | None = None

    class Settings:
        name = "medical_reports"
