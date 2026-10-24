from bson import ObjectId
from fastapi import HTTPException
import pytest

from app.common.roles import Role
from app.dependencies import owns_patient_record, require_roles


@pytest.mark.asyncio
async def test_require_roles_returns_active_user_with_allowed_role():
    user = {"_id": ObjectId(), "role": "doctor", "status": "active"}
    dependency = require_roles(Role.DOCTOR, Role.SECRETARY)

    assert await dependency(user) is user


@pytest.mark.asyncio
async def test_require_roles_rejects_disallowed_role():
    dependency = require_roles(Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        await dependency({"role": "doctor", "status": "active"})

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Rôle non autorisé."


@pytest.mark.asyncio
@pytest.mark.parametrize("account_status", ["pending", "disabled"])
async def test_require_roles_rejects_non_active_user(account_status):
    dependency = require_roles(Role.PATIENT)

    with pytest.raises(HTTPException) as exc_info:
        await dependency({"role": "patient", "status": account_status})

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Le compte n'est pas actif."


def test_owns_patient_record_allows_patient_own_record():
    owns_patient_record(
        {"role": "patient", "patient_id": "patient-1"},
        "patient-1",
    )


def test_owns_patient_record_rejects_other_patient_record():
    with pytest.raises(HTTPException) as exc_info:
        owns_patient_record(
            {"role": "patient", "patient_id": "patient-1"},
            "patient-2",
        )

    assert exc_info.value.status_code == 403


def test_owns_patient_record_rejects_patient_without_linked_record():
    with pytest.raises(HTTPException) as exc_info:
        owns_patient_record(
            {"role": "patient", "patient_id": None},
            "patient-1",
        )

    assert exc_info.value.status_code == 403


def test_owns_patient_record_does_not_restrict_staff():
    owns_patient_record({"role": "doctor", "patient_id": None}, "patient-1")
