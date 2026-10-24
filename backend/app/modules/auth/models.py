from enum import Enum

from beanie import Document, Insert, PydanticObjectId, Replace, Save, before_event
from pydantic import AwareDatetime, Field

from app.core.models import CamelModel, CreatedAtDocument, TimestampedDocument, normalize_email

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
HHMM_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class Role(str, Enum):
    ADMIN = "ADMIN"
    SECRETARY = "SECRETARY"
    DOCTOR = "DOCTOR"
    ADMIN_STAFF = "ADMIN_STAFF"


class Availability(CamelModel):
    day_of_week: int = Field(ge=1, le=7, description="1 = Monday")
    start_time: str = Field(pattern=HHMM_PATTERN)
    end_time: str = Field(pattern=HHMM_PATTERN)
    slot_minutes: int = Field(ge=5, le=240)


class DoctorProfile(CamelModel):
    specialty: str = Field(max_length=100)
    phone: str | None = None
    office_room: str | None = None
    availabilities: list[Availability] = Field(default_factory=list)


class User(TimestampedDocument):
    email: str = Field(pattern=EMAIL_PATTERN)
    password_hash: str = Field(min_length=50, description="BCrypt hash, never plain text")
    first_name: str = Field(max_length=80)
    last_name: str = Field(max_length=80)
    role: Role
    is_active: bool = True
    failed_login_attempts: int = Field(default=0, ge=0)
    locked_until: AwareDatetime | None = None
    last_login_at: AwareDatetime | None = None
    doctor_profile: DoctorProfile | None = Field(default=None, description="only for DOCTOR")

    @before_event(Insert, Replace, Save)
    def _normalize_email(self) -> None:
        self.email = normalize_email(self.email)

    class Settings:
        name = "users"


class RefreshToken(CreatedAtDocument):
    user_id: PydanticObjectId
    token_hash: str = Field(description="SHA-256 of the raw token")
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    replaced_by_token_hash: str | None = None
    user_agent: str | None = Field(default=None, max_length=255)
    ip_address: str | None = Field(default=None, max_length=45)

    class Settings:
        name = "refresh_tokens"


class Counter(Document):
    """Sequence generator; `_id` is the sequence name (e.g. "patient_record")."""

    id: str  # type: ignore[assignment]
    seq: int

    class Settings:
        name = "counters"
