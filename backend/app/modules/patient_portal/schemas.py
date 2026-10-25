"""API schemas of the patient portal and of the patient accounts (camelCase)."""

from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from app.modules.auth.models import EMAIL_PATTERN
from app.modules.followup.models import TaskStatus
from app.modules.patients.models import BloodType, Gender
from app.modules.patients.schemas import Clean, InputModel, OutputModel, _max_length

Email = Annotated[str | None, Clean, _max_length(254), Field(pattern=EMAIL_PATTERN)]


class AccountCreate(InputModel):
    """Without `email`, the email of the patient record is used."""

    email: Email = None


class AccountOut(OutputModel):
    exists: bool
    user_id: str | None = None
    email: str | None = None
    is_active: bool | None = None
    must_change_password: bool | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class AccountCredentials(AccountOut):
    """Returned once, when the account is created or its password reset: never stored."""

    temporary_password: str


class PortalProfile(OutputModel):
    """The patient's own record, without the clinic's internal notes."""

    patient_id: str
    record_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    blood_type: BloodType | None
    phone: str | None
    email: str | None
    city: str | None
    insurance_provider: str | None
    insurance_number: str | None


class PortalFollowUp(OutputModel):
    id: str
    description: str
    due_date: datetime | None
    status: TaskStatus
