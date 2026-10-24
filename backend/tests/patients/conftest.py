from typing import Any

import pytest

from app.modules.auth.models import Role, User


@pytest.fixture
def auth(token_factory):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_factory(user)}"}

    return headers


@pytest.fixture
async def secretary(user_factory) -> User:
    return await user_factory(email="secretary@example.test", role=Role.SECRETARY)


@pytest.fixture
async def doctor(user_factory) -> User:
    return await user_factory(email="doctor@example.test", role=Role.DOCTOR)


@pytest.fixture
async def admin(user_factory) -> User:
    return await user_factory(email="admin@example.test", role=Role.ADMIN)


@pytest.fixture
def payload():
    def build(**overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "firstName": "Leila",
            "lastName": "Haddad",
            "dateOfBirth": "1990-01-01",
            "gender": "FEMALE",
            "nationalId": "01234567",
            "phone": "+216 20 123 456",
            "email": "leila.haddad@example.test",
            "address": {"street": "12 rue de Marseille", "city": "Tunis", "postalCode": "1000"},
            "bloodType": "A+",
            "insurance": {"provider": "CNAM", "number": "CN-100245"},
            "emergencyContact": {
                "name": "Karim Haddad",
                "phone": "22 987 654",
                "relation": "Époux",
            },
            "administrativeNotes": "Préfère les rendez-vous le matin.",
        }
        body.update(overrides)
        return {key: value for key, value in body.items() if value is not ...}

    return build


@pytest.fixture
def create_patient(api_client, secretary, auth, payload):
    """POST /api/patients as the secretary; returns the created patient JSON."""

    async def create(**overrides: Any) -> dict[str, Any]:
        response = await api_client.post(
            "/api/patients", headers=auth(secretary), json=payload(**overrides)
        )
        assert response.status_code == 201, response.text
        return response.json()

    return create
