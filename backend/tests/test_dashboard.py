from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_admin_dashboard_summary(client, mock_database, user_factory, token_factory):
    admin = await user_factory(email="admin@example.test", role="admin")
    await user_factory(
        email="pending@example.test",
        role="doctor",
        status="pending",
    )
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    response = await client.get("/api/dashboard/summary", headers=headers)
    body = response.json()
    metrics = {item["key"]: item["value"] for item in body["kpis"]}

    assert response.status_code == 200
    assert body["role"] == "admin"
    assert body["full_name"] == "Test User"
    assert metrics["total_users"] == 2
    assert metrics["pending_users"] == 1
    assert metrics["users_by_role"]["admin"] == 1
    assert metrics["users_by_role"]["doctor"] == 1
    assert body["alerts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["doctor", "secretary"])
async def test_staff_dashboard_counts_patients_and_today_appointments(
    client,
    mock_database,
    user_factory,
    token_factory,
    role,
):
    staff = await user_factory(email=f"{role}@example.test", role=role)
    await mock_database["patients"].insert_one({"full_name": "Patient"})
    today = datetime.now(UTC)
    await mock_database["appointments"].insert_one(
        {"scheduled_at": today + timedelta(hours=1)},
    )
    await mock_database["appointments"].insert_one(
        {"scheduled_at": today - timedelta(days=1)},
    )
    headers = {"Authorization": f"Bearer {token_factory(str(staff['_id']), role)}"}

    response = await client.get("/api/dashboard/summary", headers=headers)
    body = response.json()
    metrics = {item["key"]: item["value"] for item in body["kpis"]}

    assert response.status_code == 200
    assert body["role"] == role
    assert metrics == {"patients": 1, "appointments_today": 1}
    assert body["alerts"] == []


@pytest.mark.asyncio
async def test_patient_dashboard_lists_only_own_upcoming_appointments(
    client,
    mock_database,
    user_factory,
    token_factory,
):
    patient_id = "patient-record-1"
    patient = await user_factory(
        email="patient@example.test",
        role="patient",
        patient_id=patient_id,
    )
    now = datetime.now(UTC)
    await mock_database["appointments"].insert_one(
        {
            "patient_id": patient_id,
            "scheduled_at": now + timedelta(days=2),
            "reason": "Consultation",
            "private_note": "Must not be exposed",
        },
    )
    await mock_database["appointments"].insert_one(
        {
            "patient_id": "another-patient",
            "scheduled_at": now + timedelta(days=1),
            "reason": "Other patient's appointment",
        },
    )
    headers = {"Authorization": f"Bearer {token_factory(str(patient['_id']), 'patient')}"}

    response = await client.get("/api/dashboard/summary", headers=headers)
    body = response.json()
    appointment = body["alerts"][0]

    assert response.status_code == 200
    assert body["role"] == "patient"
    assert body["kpis"][0]["value"] == 1
    assert len(body["alerts"]) == 1
    assert appointment["reason"] == "Consultation"
    assert "private_note" not in appointment
    assert "patient_id" not in appointment


@pytest.mark.asyncio
async def test_unlinked_patient_gets_message_and_empty_appointment_list(
    client,
    mock_database,
    user_factory,
    token_factory,
):
    patient = await user_factory(email="unlinked@example.test", role="patient")
    headers = {"Authorization": f"Bearer {token_factory(str(patient['_id']), 'patient')}"}
    await mock_database["appointments"].insert_one(
        {
            "patient_id": "some-patient",
            "scheduled_at": datetime.now(UTC) + timedelta(days=1),
        },
    )

    response = await client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == 200
    assert response.json()["kpis"][0]["value"] == 0
    assert response.json()["alerts"] == [
        {
            "key": "patient_record_unlinked",
            "message": "Dossier patient non lié, contactez l'accueil",
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("account_status", ["pending", "disabled"])
async def test_non_active_accounts_are_rejected_even_with_valid_token(
    client,
    user_factory,
    token_factory,
    account_status,
):
    user = await user_factory(
        email=f"{account_status}@example.test",
        status=account_status,
    )
    headers = {"Authorization": f"Bearer {token_factory(str(user['_id']), 'patient')}"}

    response = await client.get("/api/dashboard/summary", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Le compte n'est pas actif."


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client):
    response = await client.get("/api/dashboard/summary")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["doctor", "secretary"])
async def test_missing_collections_are_reported_as_zero(
    client,
    user_factory,
    token_factory,
    role,
):
    user = await user_factory(email=f"{role}@example.test", role=role)
    headers = {"Authorization": f"Bearer {token_factory(str(user['_id']), role)}"}

    response = await client.get("/api/dashboard/summary", headers=headers)
    metrics = {item["key"]: item["value"] for item in response.json()["kpis"]}

    assert response.status_code == 200
    assert metrics == {"patients": 0, "appointments_today": 0}
