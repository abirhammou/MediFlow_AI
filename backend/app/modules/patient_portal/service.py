"""Patient accounts (created by the clinic) and the patient's own portal data.

Everything a PATIENT reads here comes from `user.patient_id`, never from the request.
"""

import secrets
import string

from beanie import PydanticObjectId
from beanie.operators import Eq, In
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.core.time import utcnow
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_by_email
from app.modules.followup.models import FollowupTask, TaskStatus
from app.modules.patient_portal.models import PatientAccount
from app.modules.patient_portal.schemas import (
    AccountCreate,
    AccountCredentials,
    AccountOut,
    PortalFollowUp,
    PortalProfile,
)
from app.modules.patients import repository as patients
from app.modules.patients.dates import from_mongo_date
from app.modules.patients.models import Patient
from app.security import hash_password

# No 0/O, 1/l/I: the temporary password is read aloud or copied by hand.
PASSWORD_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
TEMPORARY_PASSWORD_LENGTH = 12
VISIBLE_TASKS = [TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value, TaskStatus.DONE.value]


def temporary_password() -> str:
    while True:
        password = "".join(
            secrets.choice(PASSWORD_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH)
        )
        if any(c.isdigit() for c in password) and any(c.isalpha() for c in password):
            return password


async def _patient(patient_id: str) -> Patient:
    try:
        pid = PydanticObjectId(patient_id)
    except (InvalidId, TypeError):
        raise APIError(404, "patient_not_found", "Dossier patient introuvable.") from None
    patient = await patients.get_patient(pid)
    if patient is None:
        raise APIError(404, "patient_not_found", "Dossier patient introuvable.")
    return patient


async def _own_patient(user: User) -> Patient:
    if user.patient_id is None:
        raise APIError(
            404, "no_patient_record", "Votre compte n'est relié à aucun dossier patient."
        )
    patient = await patients.get_patient(user.patient_id)
    if patient is None:
        raise APIError(404, "no_patient_record", "Votre dossier patient n'est plus disponible.")
    return patient


def _account_out(user: User | None, account: PatientAccount | None) -> AccountOut:
    if user is None:
        return AccountOut(exists=False)
    return AccountOut(
        exists=True,
        user_id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        must_change_password=account.must_change_password if account else False,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


class PatientAccountService:
    async def _linked_user(self, patient: Patient) -> User | None:
        return await User.find_one(Eq(User.patient_id, patient.id), Eq(User.role, Role.PATIENT))

    async def get(self, patient_id: str) -> AccountOut:
        patient = await _patient(patient_id)
        user = await self._linked_user(patient)
        account = await PatientAccount.find_one(Eq(PatientAccount.patient_id, patient.id))
        return _account_out(user, account)

    async def create(self, by: User, patient_id: str, data: AccountCreate) -> AccountCredentials:
        patient = await _patient(patient_id)
        if await self._linked_user(patient) is not None:
            raise APIError(409, "account_exists", "Ce patient a déjà un compte.")
        email = data.email or patient.email
        if not email:
            raise APIError(
                422, "email_required", "Indiquez l'email du patient (le dossier n'en a pas)."
            )
        if await get_user_by_email(email) is not None:
            raise APIError(409, "email_taken", "Un compte existe déjà avec cet email.")

        password = temporary_password()
        try:
            user = await User(
                email=email,
                password_hash=hash_password(password),
                first_name=patient.first_name,
                last_name=patient.last_name,
                role=Role.PATIENT,
                is_active=True,
                patient_id=patient.id,
            ).insert()
        except DuplicateKeyError:
            raise APIError(409, "email_taken", "Un compte existe déjà avec cet email.") from None
        account = await PatientAccount(
            user_id=user.id,
            patient_id=patient.id,
            must_change_password=True,
            temporary_password_issued_at=utcnow(),
            issued_by=by.id,
        ).insert()
        return AccountCredentials(
            **_account_out(user, account).model_dump(), temporary_password=password
        )

    async def reset_password(self, by: User, patient_id: str) -> AccountCredentials:
        """New temporary password (forgotten password, or a first one never used)."""
        patient = await _patient(patient_id)
        user = await self._linked_user(patient)
        if user is None:
            raise APIError(404, "account_not_found", "Ce patient n'a pas encore de compte.")
        password = temporary_password()
        user.password_hash = hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        await user.save()
        account = await PatientAccount.find_one(Eq(PatientAccount.user_id, user.id))
        now = utcnow()
        if account is None:  # an account from self sign-up, linked later
            account = PatientAccount(user_id=user.id, patient_id=patient.id)  # type: ignore[arg-type]
        account.must_change_password = True
        account.temporary_password_issued_at = now
        account.issued_by = by.id
        await account.save()
        return AccountCredentials(
            **_account_out(user, account).model_dump(), temporary_password=password
        )


class PortalService:
    async def profile(self, user: User) -> PortalProfile:
        patient = await _own_patient(user)
        return PortalProfile(
            patient_id=str(patient.id),
            record_number=patient.record_number,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=from_mongo_date(patient.date_of_birth),
            gender=patient.gender,
            blood_type=patient.blood_type,
            phone=patient.phone,
            email=patient.email,
            city=patient.address.city if patient.address else None,
            insurance_provider=patient.insurance.provider if patient.insurance else None,
            insurance_number=patient.insurance.number if patient.insurance else None,
        )

    async def follow_ups(self, user: User) -> list[PortalFollowUp]:
        patient = await _own_patient(user)
        tasks = (
            await FollowupTask.find(
                Eq(FollowupTask.patient_id, patient.id), In(FollowupTask.status, VISIBLE_TASKS)
            )
            .sort([("dueDate", 1)])
            .to_list()
        )
        return [
            PortalFollowUp(
                id=str(task.id),
                description=task.description,
                due_date=task.due_date,
                status=task.status,
            )
            for task in tasks
        ]
