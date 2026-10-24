import pytest
from beanie import PydanticObjectId
from fastapi import HTTPException

from app.dependencies import get_current_user, owns_patient_record, require_roles
from app.modules.auth.models import Role, User
from app.security import create_access_token

PATIENT_ID = PydanticObjectId()


def make_user(role: Role, patient_id: PydanticObjectId | None = None) -> User:
    return User.model_construct(role=role, is_active=True, patient_id=patient_id)


async def test_require_roles_returns_user_with_allowed_role():
    user = make_user(Role.DOCTOR)
    dependency = require_roles(Role.DOCTOR, Role.SECRETARY)

    assert await dependency(user) is user


async def test_require_roles_rejects_disallowed_role():
    dependency = require_roles(Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(make_user(Role.DOCTOR))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Rôle non autorisé."


async def test_get_current_user_rejects_inactive_account(user_factory):
    user = await user_factory(role=Role.DOCTOR, is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(create_access_token(str(user.id), user.role.value))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Le compte n'est pas actif."


async def test_get_current_user_rejects_malformed_subject(db):
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(create_access_token("not-an-object-id", "ADMIN"))

    assert exc_info.value.status_code == 401


def test_owns_patient_record_allows_patient_own_record():
    owns_patient_record(make_user(Role.PATIENT, PATIENT_ID), str(PATIENT_ID))


def test_owns_patient_record_rejects_other_patient_record():
    with pytest.raises(HTTPException) as exc_info:
        owns_patient_record(make_user(Role.PATIENT, PATIENT_ID), str(PydanticObjectId()))

    assert exc_info.value.status_code == 403


def test_owns_patient_record_rejects_patient_without_linked_record():
    with pytest.raises(HTTPException) as exc_info:
        owns_patient_record(make_user(Role.PATIENT), str(PATIENT_ID))

    assert exc_info.value.status_code == 403


def test_owns_patient_record_does_not_restrict_staff():
    owns_patient_record(make_user(Role.DOCTOR), str(PATIENT_ID))
