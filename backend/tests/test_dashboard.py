from datetime import date, timedelta

import pytest

from app.core.sequence import next_record_number
from app.core.time import utc_midnight, utcnow
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.auth.models import Role, User
from app.modules.patients.models import Gender, Patient


@pytest.fixture
def auth(token_factory):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_factory(user)}"}

    return headers


async def make_patient(**fields) -> Patient:
    return await Patient(
        record_number=await next_record_number(),
        first_name="Leila",
        last_name="Haddad",
        date_of_birth=date(1990, 5, 1),
        gender=Gender.FEMALE,
        **fields,
    ).insert()


async def make_appointment(patient: Patient, doctor: User, start_at, **fields) -> Appointment:
    return await Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
        **fields,
    ).insert()


async def summary(api_client, headers):
    response = await api_client.get("/api/dashboard/summary", headers=headers)
    body = response.json()
    return response, body, {item["key"]: item["value"] for item in body.get("kpis", [])}


async def test_admin_dashboard_summary(api_client, user_factory, auth):
    admin = await user_factory(email="admin@example.test", role=Role.ADMIN)
    await user_factory(email="pending@example.test", role=Role.DOCTOR, is_active=False)

    response, body, metrics = await summary(api_client, auth(admin))

    assert response.status_code == 200
    assert body["role"] == "ADMIN"
    assert body["full_name"] == "Test User"
    assert metrics["total_users"] == 2
    assert metrics["inactive_users"] == 1
    assert metrics["users_by_role"]["ADMIN"] == metrics["users_by_role"]["DOCTOR"] == 1
    assert metrics["users_by_role"]["PATIENT"] == 0
    assert body["alerts"] == []


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF])
async def test_staff_dashboard_counts_patients_and_today_appointments(
    api_client, user_factory, auth, role
):
    staff = await user_factory(email="staff@example.test", role=role)
    doctor = await user_factory(email="doctor@example.test", role=Role.DOCTOR)
    patient = await make_patient()
    await make_patient(deleted_at=utcnow())
    noon = utc_midnight(utcnow().date()) + timedelta(hours=12)
    await make_appointment(patient, doctor, noon)
    await make_appointment(patient, doctor, noon + timedelta(hours=1), status=AppointmentStatus.CANCELLED)
    await make_appointment(patient, doctor, noon - timedelta(days=1))

    response, body, metrics = await summary(api_client, auth(staff))

    assert response.status_code == 200
    assert body["role"] == role.value
    assert metrics == {"patients": 1, "appointments_today": 1}


async def test_patient_dashboard_lists_only_own_upcoming_appointments(
    api_client, user_factory, auth
):
    doctor = await user_factory(email="doctor@example.test", role=Role.DOCTOR)
    own, other = await make_patient(), await make_patient()
    account = await user_factory(email="patient@example.test", role=Role.PATIENT, patient_id=own.id)
    now = utcnow()
    await make_appointment(own, doctor, now + timedelta(days=2), reason="Consultation")
    await make_appointment(own, doctor, now - timedelta(days=2), reason="Past")
    await make_appointment(other, doctor, now + timedelta(days=1), reason="Other patient")

    response, body, metrics = await summary(api_client, auth(account))

    assert response.status_code == 200
    assert body["role"] == "PATIENT"
    assert metrics["upcoming_appointments"] == 1
    assert [alert["reason"] for alert in body["alerts"]] == ["Consultation"]
    assert "patient_id" not in body["alerts"][0]


async def test_unlinked_patient_gets_message(api_client, user_factory, auth):
    account = await user_factory(email="unlinked@example.test", role=Role.PATIENT)

    response, body, metrics = await summary(api_client, auth(account))

    assert response.status_code == 200
    assert metrics["upcoming_appointments"] == 0
    assert body["alerts"] == [
        {"key": "patient_record_unlinked", "message": "Dossier patient non lié, contactez l'accueil"}
    ]


async def test_inactive_account_is_rejected_even_with_valid_token(api_client, user_factory, auth):
    user = await user_factory(email="inactive@example.test", is_active=False)

    response = await api_client.get("/api/dashboard/summary", headers=auth(user))

    assert response.status_code == 403
    assert response.json()["detail"] == "Le compte n'est pas actif."


async def test_dashboard_requires_authentication(api_client):
    response = await api_client.get("/api/dashboard/summary")

    assert response.status_code == 401
