from datetime import UTC, datetime, timedelta

import jwt
import pytest
from bson import ObjectId

from app.config import settings
from app.security import create_access_token


@pytest.mark.asyncio
async def test_register_patient_creates_user(client, mock_database):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "Patient@Example.test",
            "password": "patient-password",
            "full_name": "Pat Example",
        },
    )

    assert response.status_code == 201
    profile = response.json()
    assert profile["email"] == "patient@example.test"
    assert profile["role"] == "patient"
    assert profile["status"] == "active"
    assert profile["patient_id"] is None
    assert "password_hash" not in profile

    user = await mock_database["users"].find_one({"_id": ObjectId(profile["id"])})
    assert user is not None
    assert user["email"] == "patient@example.test"
    assert user["full_name"] == "Pat Example"
    assert user["patient_id"] is None
    assert "password_hash" in user
    assert await mock_database["patients"].count_documents({}) == 0


@pytest.mark.asyncio
async def test_register_doctor_is_pending_and_login_requires_approval(
    client,
    mock_database,
):
    registration = await client.post(
        "/api/auth/register",
        json={
            "email": "doctor@example.test",
            "password": "doctor-password",
            "full_name": "Dr Example",
            "role_requested": "doctor",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == "doctor"
    assert registration.json()["status"] == "pending"

    login = await client.post(
        "/api/auth/login",
        data={"username": "doctor@example.test", "password": "doctor-password"},
    )
    assert login.status_code == 403
    assert "attente d'approbation" in login.json()["detail"]

    await mock_database["users"].update_one(
        {"email": "doctor@example.test"},
        {"$set": {"status": "active"}},
    )
    approved_login = await client.post(
        "/api/auth/login",
        data={"username": "doctor@example.test", "password": "doctor-password"},
    )
    assert approved_login.status_code == 200
    assert approved_login.json()["role"] == "doctor"
    assert approved_login.json()["status"] == "active"


@pytest.mark.asyncio
async def test_disabled_account_cannot_login(client, user_factory):
    await user_factory(
        email="disabled@example.test",
        password="disabled-password",
        status="disabled",
    )

    response = await client.post(
        "/api/auth/login",
        data={"username": "disabled@example.test", "password": "disabled-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Compte désactivé."


@pytest.mark.asyncio
async def test_login_uses_same_message_for_unknown_email_and_wrong_password(
    client,
    user_factory,
):
    await user_factory(email="known@example.test", password="known-password")

    wrong_password = await client.post(
        "/api/auth/login",
        data={"username": "known@example.test", "password": "wrong-password"},
    )
    unknown_email = await client.post(
        "/api/auth/login",
        data={"username": "unknown@example.test", "password": "wrong-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


@pytest.mark.asyncio
async def test_admin_role_requested_is_forbidden(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "admin@example.test",
            "password": "admin-password",
            "full_name": "Admin Example",
            "role_requested": "admin",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "role_forbidden"


@pytest.mark.asyncio
async def test_duplicate_email_is_conflict_after_normalization(client):
    payload = {
        "email": "Duplicate@Example.test",
        "password": "duplicate-password",
        "full_name": "Duplicate Example",
    }
    first = await client.post("/api/auth/register", json=payload)
    payload["email"] = "duplicate@example.test"
    second = await client.post("/api/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "email_exists"


@pytest.mark.asyncio
async def test_me_requires_valid_token(client, user_factory, token_factory):
    user = await user_factory(email="me@example.test")

    missing = await client.get("/api/auth/me")
    authorized = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token_factory(str(user['_id']))}"},
    )
    invalid = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    expired_token = jwt.encode(
        {
            "sub": str(user["_id"]),
            "role": "patient",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    expired = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert missing.status_code == invalid.status_code == expired.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["email"] == "me@example.test"
    assert "password_hash" not in authorized.json()


@pytest.mark.asyncio
async def test_change_password_requires_current_password(client, user_factory, token_factory):
    user = await user_factory(
        email="password@example.test",
        password="initial-password",
    )
    headers = {"Authorization": f"Bearer {token_factory(str(user['_id']))}"}

    wrong_current = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={
            "current_password": "incorrect-password",
            "new_password": "replacement-password",
        },
    )
    changed = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={
            "current_password": "initial-password",
            "new_password": "replacement-password",
        },
    )
    login = await client.post(
        "/api/auth/login",
        data={
            "username": "password@example.test",
            "password": "replacement-password",
        },
    )

    assert wrong_current.status_code == 400
    assert changed.status_code == 200
    assert login.status_code == 200
