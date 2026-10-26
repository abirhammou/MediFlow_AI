from datetime import date

import pytest_asyncio

from app.modules.auth.models import Role
from app.modules.patients.models import Gender, Patient


@pytest_asyncio.fixture
async def headers(user_factory, token_factory) -> dict[str, str]:
    secretary = await user_factory(email="secretary@example.test", role=Role.SECRETARY)
    return {"Authorization": f"Bearer {token_factory(secretary)}"}


@pytest_asyncio.fixture
async def task(db) -> dict:
    patient = await Patient(
        record_number="PAT-2026-00042",
        first_name="Amira",
        last_name="Gharbi",
        date_of_birth=date(1985, 4, 12),
        gender=Gender.FEMALE,
    ).insert()
    return {
        "description": "Rappeler la patiente pour reprogrammer l'échographie",
        "due_date": "2026-11-03",
        "patient_id": str(patient.id),
        "appointment_date": "2026-11-10",
        "appointment_reason": "Échographie cardiaque",
    }


async def test_tasks_pass_the_schema_validator(api_client, db, task, headers):
    created = await api_client.post("/api/follow-up/tasks", json=task, headers=headers)
    stored = await db["followup_tasks"].find_one()

    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert created.json()["patient_record_number"] == "PAT-2026-00042"
    assert stored["status"] == "TODO" and stored["patientName"] == "Amira Gharbi"
    assert str(stored["patientId"]) == task["patient_id"]
    assert stored["dueDate"].date() == date(2026, 11, 3)


async def test_unknown_patient_is_refused(api_client, task, headers):
    response = await api_client.post(
        "/api/follow-up/tasks",
        json={**task, "patient_id": "0123456789abcdef01234567"},
        headers=headers,
    )

    assert response.status_code == 404


async def test_task_round_trip(api_client, task, headers):
    created = (await api_client.post("/api/follow-up/tasks", json=task, headers=headers)).json()
    await api_client.post(
        "/api/follow-up/tasks", json={**task, "due_date": "2026-11-01"}, headers=headers
    )

    done = await api_client.patch(
        f"/api/follow-up/tasks/{created['id']}", json={"status": "done"}, headers=headers
    )
    listing = await api_client.get("/api/follow-up/tasks", headers=headers)
    pending = await api_client.get("/api/follow-up/tasks", params={"status": "pending"}, headers=headers)
    stats = await api_client.get("/api/follow-up/tasks/stats", headers=headers)

    assert done.status_code == 200 and done.json()["status"] == "done"
    assert [item["due_date"] for item in listing.json()] == ["2026-11-01", "2026-11-03"]
    assert len(pending.json()) == 1
    assert stats.json() == {"total": 2, "pending": 1, "done": 1, "cancelled": 0}
