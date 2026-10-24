from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_by_email
from app.modules.auth.service import MAX_FAILED_LOGINS
from app.modules.patients.models import Patient


def login(api_client, email: str, password: str):
    return api_client.post("/api/auth/login", data={"username": email, "password": password})


def register_payload(email: str, **fields) -> dict:
    return {
        "email": email,
        "password": "register-password",
        "first_name": "Pat",
        "last_name": "Example",
        **fields,
    }


async def test_register_patient_creates_active_user(api_client):
    response = await api_client.post(
        "/api/auth/register", json=register_payload("Patient@Example.test")
    )

    assert response.status_code == 201
    profile = response.json()
    assert profile["email"] == "patient@example.test"
    assert profile["role"] == "PATIENT"
    assert profile["is_active"] is True
    assert profile["patient_id"] is None
    assert "password_hash" not in profile

    user = await User.get(profile["id"])
    assert user.first_name == "Pat"
    assert user.password_hash.startswith("$2")
    assert await Patient.count() == 0


async def test_register_doctor_is_inactive_until_approved(api_client):
    registration = await api_client.post(
        "/api/auth/register",
        json=register_payload("doctor@example.test", role_requested="DOCTOR"),
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == "DOCTOR"
    assert registration.json()["is_active"] is False

    pending = await login(api_client, "doctor@example.test", "register-password")
    assert pending.status_code == 403
    assert "attente d'approbation" in pending.json()["detail"]

    user = await get_user_by_email("doctor@example.test")
    user.is_active = True
    await user.save()
    approved = await login(api_client, "doctor@example.test", "register-password")
    assert approved.status_code == 200
    assert approved.json()["role"] == "DOCTOR"
    assert approved.json()["first_name"] == "Pat"


async def test_disabled_account_cannot_login(api_client, user_factory):
    await user_factory(email="disabled@example.test", password="disabled-password", is_active=False)

    response = await login(api_client, "disabled@example.test", "disabled-password")

    assert response.status_code == 403


async def test_login_uses_same_message_for_unknown_email_and_wrong_password(
    api_client, user_factory
):
    await user_factory(email="known@example.test", password="known-password")

    wrong_password = await login(api_client, "known@example.test", "wrong-password")
    unknown_email = await login(api_client, "unknown@example.test", "wrong-password")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


async def test_successful_login_records_last_login_and_resets_failures(api_client, user_factory):
    user = await user_factory(email="track@example.test", password="track-password")
    await login(api_client, "track@example.test", "wrong-password")
    assert (await User.get(user.id)).failed_login_attempts == 1

    response = await login(api_client, "Track@Example.test", "track-password")

    assert response.status_code == 200
    stored = await User.get(user.id)
    assert stored.failed_login_attempts == 0
    assert stored.last_login_at is not None


async def test_account_is_locked_after_repeated_failures(api_client, user_factory):
    await user_factory(email="locked@example.test", password="locked-password")

    for _ in range(MAX_FAILED_LOGINS):
        await login(api_client, "locked@example.test", "wrong-password")
    locked = await login(api_client, "locked@example.test", "locked-password")

    assert locked.status_code == 423
    user = await get_user_by_email("locked@example.test")
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await user.save()
    assert (await login(api_client, "locked@example.test", "locked-password")).status_code == 200


async def test_admin_and_admin_staff_roles_cannot_self_register(api_client):
    for role in ("ADMIN", "ADMIN_STAFF"):
        response = await api_client.post(
            "/api/auth/register",
            json=register_payload(f"{role.lower()}@example.test", role_requested=role),
        )

        assert response.status_code == 403
        assert response.json()["code"] == "role_forbidden"


async def test_duplicate_email_is_conflict_after_normalization(api_client):
    first = await api_client.post(
        "/api/auth/register", json=register_payload("Duplicate@Example.test")
    )
    second = await api_client.post(
        "/api/auth/register", json=register_payload("duplicate@example.test")
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "email_exists"


async def test_me_requires_valid_token(api_client, user_factory, token_factory):
    user = await user_factory(email="me@example.test")
    expired_token = jwt.encode(
        {"sub": str(user.id), "role": "PATIENT", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )

    missing = await api_client.get("/api/auth/me")
    invalid = await api_client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    expired = await api_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    authorized = await api_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token_factory(user)}"}
    )

    assert missing.status_code == invalid.status_code == expired.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["email"] == "me@example.test"
    assert "password_hash" not in authorized.json()


async def test_me_rejects_account_disabled_after_token_issue(
    api_client, user_factory, token_factory
):
    user = await user_factory(email="disabled-after-token@example.test")
    token = token_factory(user)
    user.is_active = False
    await user.save()

    response = await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Le compte n'est pas actif."


async def test_change_password_requires_current_password(api_client, user_factory, token_factory):
    user = await user_factory(email="password@example.test", password="initial-password")
    headers = {"Authorization": f"Bearer {token_factory(user)}"}

    wrong_current = await api_client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "incorrect-password", "new_password": "replacement-password"},
    )
    changed = await api_client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "initial-password", "new_password": "replacement-password"},
    )

    assert wrong_current.status_code == 400
    assert changed.status_code == 200
    assert (await login(api_client, "password@example.test", "replacement-password")).status_code == 200


async def test_staff_role_is_stored_uppercase(user_factory):
    user = await user_factory(email="staff@example.test", role=Role.ADMIN_STAFF)

    raw = await User.get_pymongo_collection().find_one({"_id": user.id})

    assert raw["role"] == "ADMIN_STAFF"
    assert raw["isActive"] is True
