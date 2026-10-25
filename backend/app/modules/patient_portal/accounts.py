"""Temporary-password state of the PATIENT accounts (used by auth and require_roles)."""

from beanie.operators import Eq, Set

from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.patient_portal.models import PatientAccount


async def needs_password_change(user: User) -> bool:
    """True while a clinic-created PATIENT account still has its temporary password."""
    if user.role != Role.PATIENT or user.id is None:
        return False
    account = await PatientAccount.find_one(Eq(PatientAccount.user_id, user.id))
    return account is not None and account.must_change_password


async def mark_password_changed(user: User) -> None:
    if user.role == Role.PATIENT and user.id is not None:
        await PatientAccount.find(Eq(PatientAccount.user_id, user.id)).update_many(
            Set({"mustChangePassword": False, "updatedAt": utcnow()})
        )
