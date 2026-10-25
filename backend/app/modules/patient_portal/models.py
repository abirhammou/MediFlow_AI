from beanie import PydanticObjectId
from pydantic import AwareDatetime

from app.core.models import TimestampedDocument


class PatientAccount(TimestampedDocument):
    """A PATIENT login created by the clinic for a record (not by self sign-up).

    `must_change_password` stays true until the patient replaces the temporary password:
    meanwhile only /api/auth/me and /api/auth/change-password answer.
    """

    user_id: PydanticObjectId
    patient_id: PydanticObjectId
    must_change_password: bool = True
    temporary_password_issued_at: AwareDatetime | None = None
    issued_by: PydanticObjectId | None = None

    class Settings:
        name = "patient_accounts"
