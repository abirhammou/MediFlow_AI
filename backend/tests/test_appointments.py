"""Tests du module appointments.

Ils tournent sans Docker ni MongoDB : une base simulée (mongomock) remplace MongoDB.
`list_collection_names` est adaptée car Beanie lui passe un argument que mongomock ne
connaît pas encore.
"""

from datetime import UTC, date, datetime, time, timedelta

import mongomock.database as mongomock_database
import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core.db import DOCUMENT_MODELS
from app.errors import LLMResponseError
from app.main import app
from app.modules.appointments import service as appointment_service
from app.modules.appointments.models import AppointmentRequest, AppointmentStatus, DayPart
from app.modules.appointments.schemas import AppointmentIntent
from app.modules.appointments.slots import CLINIC_TZ, compute_free_slots
from app.modules.auth.models import Availability, DoctorProfile, Role, User
from app.modules.patients.models import Gender, Patient
from app.security import create_access_token, hash_password

PASSWORD_HASH = hash_password("password-123")


# ── Outils ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def database(monkeypatch):
    original = mongomock_database.Database.list_collection_names
    monkeypatch.setattr(
        mongomock_database.Database,
        "list_collection_names",
        lambda self, *args, **kwargs: original(self),
    )
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(
        database=client["mediflow_test"], document_models=DOCUMENT_MODELS, skip_indexes=True
    )
    yield client["mediflow_test"]
    client.close()


@pytest_asyncio.fixture
async def http(database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def make_user(email: str, role: Role, **extra) -> User:
    return await User(
        email=email,
        password_hash=PASSWORD_HASH,
        first_name=role.value.title(),
        last_name="Test",
        role=role,
        **extra,
    ).insert()


async def make_doctor(email: str = "doctor@example.test", specialty: str = "Cardiologie") -> User:
    availabilities = [
        Availability(day_of_week=day, start_time="09:00", end_time="12:00", slot_minutes=30)
        for day in range(1, 8)
    ]
    return await make_user(
        email,
        Role.DOCTOR,
        doctor_profile=DoctorProfile(specialty=specialty, availabilities=availabilities),
    )


async def make_patient(number: int = 1) -> Patient:
    return await Patient(
        record_number=f"PAT-2026-{number:05d}",
        first_name="Patient",
        last_name=f"Numero{number}",
        date_of_birth=date(1990, 1, 1),
        gender=Gender.FEMALE,
    ).insert()


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


def local_day(days_ahead: int = 7) -> date:
    return datetime.now(CLINIC_TZ).date() + timedelta(days=days_ahead)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Une heure locale de la clinique, exprimée en UTC."""
    return datetime.combine(day, time(hour, minute), tzinfo=CLINIC_TZ).astimezone(UTC)


def body(patient: Patient, doctor: User, start: datetime, **extra) -> dict:
    return {
        "patient_id": str(patient.id),
        "doctor_id": str(doctor.id),
        "start_at": start.isoformat(),
        **extra,
    }


@pytest_asyncio.fixture
async def staff(database):
    secretary = await make_user("secretary@example.test", Role.SECRETARY)
    doctor = await make_doctor()
    patient = await make_patient()
    return secretary, doctor, patient


# ── Droits ────────────────────────────────────────────────────────────────────


async def test_routes_require_authentication(http):
    assert (await http.get("/api/appointments")).status_code == 401
    assert (await http.post("/api/appointments", json={})).status_code == 401
    assert (await http.post("/api/appointments/parse-request", json={})).status_code == 401


async def test_patient_cannot_update_but_staff_can(http, staff):
    secretary, doctor, patient = staff
    created = await http.post(
        "/api/appointments", json=body(patient, doctor, at(local_day(), 9)), headers=auth(secretary)
    )
    appointment_id = created.json()["id"]
    patient_user = await make_user("patient@example.test", Role.PATIENT, patient_id=patient.id)

    denied = await http.put(
        f"/api/appointments/{appointment_id}", json={"reason": "x"}, headers=auth(patient_user)
    )
    allowed = await http.put(
        f"/api/appointments/{appointment_id}", json={"reason": "Contrôle"}, headers=auth(secretary)
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["reason"] == "Contrôle"


async def test_patient_only_sees_and_books_own_records(http, staff):
    secretary, doctor, patient = staff
    other_patient = await make_patient(2)
    patient_user = await make_user("patient@example.test", Role.PATIENT, patient_id=patient.id)
    mine = await http.post(
        "/api/appointments", json=body(patient, doctor, at(local_day(), 9)), headers=auth(secretary)
    )
    await http.post(
        "/api/appointments",
        json=body(other_patient, doctor, at(local_day(), 10)),
        headers=auth(secretary),
    )

    listed = await http.get("/api/appointments", headers=auth(patient_user))
    foreign = await http.post(
        "/api/appointments",
        json=body(other_patient, doctor, at(local_day(), 11)),
        headers=auth(patient_user),
    )
    own = await http.post(
        "/api/appointments",
        json=body(patient, doctor, at(local_day(), 11)),
        headers=auth(patient_user),
    )

    assert [item["id"] for item in listed.json()["items"]] == [mine.json()["id"]]
    assert foreign.status_code == 403
    assert own.status_code == 201
    assert own.json()["status"] == "PENDING"  # à confirmer par le secrétariat


async def test_doctor_cannot_open_another_doctors_appointment(http, staff):
    secretary, doctor, patient = staff
    other_doctor = await make_doctor("doctor2@example.test")
    created = await http.post(
        "/api/appointments", json=body(patient, doctor, at(local_day(), 9)), headers=auth(secretary)
    )

    response = await http.get(
        f"/api/appointments/{created.json()['id']}", headers=auth(other_doctor)
    )

    assert response.status_code == 403


# ── CRUD et créneaux ──────────────────────────────────────────────────────────


async def test_create_refuses_a_taken_slot_but_allows_back_to_back(http, staff):
    secretary, doctor, patient = staff
    first = await http.post(
        "/api/appointments", json=body(patient, doctor, at(local_day(), 9)), headers=auth(secretary)
    )
    same = await http.post(
        "/api/appointments", json=body(patient, doctor, at(local_day(), 9)), headers=auth(secretary)
    )
    overlap = await http.post(
        "/api/appointments",
        json=body(patient, doctor, at(local_day(), 9, 15)),
        headers=auth(secretary),
    )
    next_slot = await http.post(
        "/api/appointments",
        json=body(patient, doctor, at(local_day(), 9, 30)),
        headers=auth(secretary),
    )

    assert first.status_code == 201
    assert first.json()["status"] == "CONFIRMED"
    assert (same.status_code, same.json()["code"]) == (409, "slot_taken")
    assert overlap.status_code == 409
    assert next_slot.status_code == 201


async def test_create_validates_input(http, staff):
    secretary, doctor, patient = staff
    start = at(local_day(), 9)

    reversed_range = await http.post(
        "/api/appointments",
        json=body(patient, doctor, start, end_at=(start - timedelta(minutes=5)).isoformat()),
        headers=auth(secretary),
    )
    in_the_past = await http.post(
        "/api/appointments",
        json=body(patient, doctor, datetime.now(UTC) - timedelta(days=1)),
        headers=auth(secretary),
    )
    unknown_doctor = await http.post(
        "/api/appointments",
        json=body(patient, secretary, start),  # la secrétaire n'est pas un médecin
        headers=auth(secretary),
    )

    assert (reversed_range.status_code, reversed_range.json()["code"]) == (
        422,
        "invalid_time_range",
    )
    assert in_the_past.json()["code"] == "appointment_in_past"
    assert unknown_doctor.json()["code"] == "doctor_not_found"


async def test_update_reschedules_and_detects_conflicts(http, staff):
    secretary, doctor, patient = staff
    day = local_day()
    first = await http.post(
        "/api/appointments", json=body(patient, doctor, at(day, 9)), headers=auth(secretary)
    )
    second = await http.post(
        "/api/appointments", json=body(patient, doctor, at(day, 10)), headers=auth(secretary)
    )

    conflict = await http.put(
        f"/api/appointments/{second.json()['id']}",
        json={"start_at": at(day, 9).isoformat()},
        headers=auth(secretary),
    )
    moved = await http.put(
        f"/api/appointments/{first.json()['id']}",
        json={"start_at": at(day, 11).isoformat(), "status": "COMPLETED"},
        headers=auth(secretary),
    )
    cancel_through_update = await http.put(
        f"/api/appointments/{first.json()['id']}",
        json={"status": "CANCELLED"},
        headers=auth(secretary),
    )

    assert conflict.status_code == 409
    assert moved.status_code == 200
    assert moved.json()["start_at"] == at(day, 11).isoformat().replace("+00:00", "Z")
    assert moved.json()["status"] == "COMPLETED"
    assert cancel_through_update.json()["code"] == "use_cancel_route"


async def test_cancel_frees_the_slot_and_keeps_history(http, staff):
    secretary, doctor, patient = staff
    start = at(local_day(), 9)
    created = await http.post(
        "/api/appointments", json=body(patient, doctor, start), headers=auth(secretary)
    )
    appointment_id = created.json()["id"]

    cancelled = await http.post(
        f"/api/appointments/{appointment_id}/cancel",
        json={"cancel_reason": "Patient indisponible"},
        headers=auth(secretary),
    )
    again = await http.post(f"/api/appointments/{appointment_id}/cancel", headers=auth(secretary))
    rebooked = await http.post(
        "/api/appointments", json=body(patient, doctor, start), headers=auth(secretary)
    )
    history = await http.get(
        f"/api/appointments/{appointment_id}", headers=auth(secretary)
    )

    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancel_reason"] == "Patient indisponible"
    assert again.status_code == 409
    assert rebooked.status_code == 201
    assert history.status_code == 200  # annuler ne supprime pas


async def test_list_filters_and_paginates(http, staff):
    secretary, doctor, patient = staff
    day = local_day()
    for hour in (9, 10, 11):
        await http.post(
            "/api/appointments", json=body(patient, doctor, at(day, hour)), headers=auth(secretary)
        )

    page = await http.get(
        "/api/appointments?page=1&page_size=2", headers=auth(secretary)
    )
    filtered = await http.get(
        "/api/appointments",
        params={"doctor_id": str(doctor.id), "date_from": at(day, 10).isoformat()},
        headers=auth(secretary),
    )

    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert page.json()["items"][0]["start_at"] < page.json()["items"][1]["start_at"]
    assert len(filtered.json()["items"]) == 2


# ── LLM : message libre -> demande structurée -> créneaux réels ───────────────


async def test_parse_request_proposes_only_real_free_slots(http, staff, monkeypatch):
    secretary, doctor, patient = staff
    day = local_day()
    await http.post(
        "/api/appointments", json=body(patient, doctor, at(day, 9)), headers=auth(secretary)
    )
    received = {}

    async def fake_llm(module, system, user, output_schema):
        received.update(module=module, user=user)
        return AppointmentIntent(
            preferred_date=day, day_part=DayPart.MORNING, specialty="cardio", reason="Contrôle"
        )

    monkeypatch.setattr(appointment_service, "generate_json", fake_llm)
    patient_user = await make_user("patient@example.test", Role.PATIENT, patient_id=patient.id)

    response = await http.post(
        "/api/appointments/parse-request",
        json={"message": "Je voudrais un rendez-vous demain matin"},
        headers=auth(patient_user),
    )

    assert response.status_code == 200
    starts = [slot["start_at"] for slot in response.json()["available_slots"]]
    assert at(day, 9).isoformat().replace("+00:00", "Z") not in starts  # déjà pris
    assert at(day, 9, 30).isoformat().replace("+00:00", "Z") in starts
    assert len(starts) == 5  # 09:30, 10:00, 10:30, 11:00, 11:30
    assert received["module"] == "appointments"
    assert "Je voudrais un rendez-vous demain matin" in received["user"]
    saved = await AppointmentRequest.get(response.json()["request_id"])
    assert saved.raw_message == "Je voudrais un rendez-vous demain matin"
    assert saved.patient_id == patient.id
    assert saved.parsed.day_part == DayPart.MORNING


async def test_parse_request_works_with_the_mock_llm(http, staff, monkeypatch):
    secretary, *_ = staff
    monkeypatch.setenv("APPOINTMENTS_LLM_PROVIDER", "mock")

    response = await http.post(
        "/api/appointments/parse-request",
        json={"message": "Un rendez-vous mardi après-midi"},
        headers=auth(secretary),
    )

    assert response.status_code == 200
    assert response.json()["available_slots"] == []  # le mock répond avec une date passée


async def test_parse_request_without_date_has_no_slots(http, staff, monkeypatch):
    secretary, *_ = staff

    async def fake_llm(**kwargs):
        return AppointmentIntent()

    monkeypatch.setattr(appointment_service, "generate_json", fake_llm)

    response = await http.post(
        "/api/appointments/parse-request",
        json={"message": "Bonjour"},
        headers=auth(secretary),
    )

    assert response.json()["available_slots"] == []
    assert response.json()["parsed"]["preferred_date"] is None


# ── Calcul des créneaux (fonctions pures) ─────────────────────────────────────


class Av:
    def __init__(self, day_of_week, start_time, end_time, slot_minutes=30):
        self.day_of_week = day_of_week
        self.start_time = start_time
        self.end_time = end_time
        self.slot_minutes = slot_minutes


MONDAY = date(2030, 1, 7)
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)


def test_slots_follow_the_weekly_availability():
    availabilities = [Av(1, "09:00", "10:00"), Av(2, "09:00", "12:00")]

    monday = compute_free_slots(availabilities, MONDAY, None, [], LONG_AGO)
    wednesday = compute_free_slots(availabilities, MONDAY + timedelta(days=2), None, [], LONG_AGO)

    assert [slot.start_at for slot in monday] == [at(MONDAY, 9), at(MONDAY, 9, 30)]
    assert wednesday == []


def test_slots_exclude_busy_ranges_past_slots_and_other_day_parts():
    availabilities = [Av(1, "09:00", "18:00", 60)]
    busy = [(at(MONDAY, 10), at(MONDAY, 11))]

    all_day = compute_free_slots(availabilities, MONDAY, None, busy, LONG_AGO)
    afternoon = compute_free_slots(availabilities, MONDAY, DayPart.AFTERNOON, [], LONG_AGO)
    evening = compute_free_slots(availabilities, MONDAY, DayPart.EVENING, [], LONG_AGO)
    started = compute_free_slots(availabilities, MONDAY, None, [], at(MONDAY, 14))

    assert at(MONDAY, 10) not in [slot.start_at for slot in all_day]
    assert len(all_day) == 8
    assert [slot.start_at for slot in afternoon] == [at(MONDAY, h) for h in (12, 13, 14, 15, 16)]
    assert [slot.start_at for slot in evening] == [at(MONDAY, 17)]
    assert [slot.start_at for slot in started][0] == at(MONDAY, 15)  # 14:00 est déjà commencé


def test_a_slot_that_does_not_fit_is_dropped():
    slots = compute_free_slots([Av(1, "09:00", "09:45")], MONDAY, None, [], LONG_AGO)

    assert [slot.start_at for slot in slots] == [at(MONDAY, 9)]


def test_appointment_status_values_match_the_database_validator():
    assert {status.value for status in AppointmentStatus} == {
        "PENDING",
        "CONFIRMED",
        "CANCELLED",
        "COMPLETED",
        "NO_SHOW",
    }


async def test_parse_request_retries_when_the_llm_fails_once(http, staff, monkeypatch):
    calls = {"n": 0}

    async def flaky_llm(module, system, user, output_schema):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMResponseError()
        return AppointmentIntent(preferred_date=None, day_part=None, specialty=None, reason=None)

    monkeypatch.setattr(appointment_service, "generate_json", flaky_llm)
    response = await http.post(
        "/api/appointments/parse-request",
        json={"message": "rdv demain"},
        headers=auth(staff[0]),
    )

    assert response.status_code == 200
    assert calls["n"] == 2


async def test_parse_request_gives_up_after_three_llm_failures(http, staff, monkeypatch):
    async def broken_llm(module, system, user, output_schema):
        raise LLMResponseError()

    monkeypatch.setattr(appointment_service, "generate_json", broken_llm)
    response = await http.post(
        "/api/appointments/parse-request",
        json={"message": "rdv demain"},
        headers=auth(staff[0]),
    )

    assert response.status_code == 502


# ── Liste des médecins ────────────────────────────────────────────────────────


async def test_doctors_list_is_readable_by_every_role_and_requires_login(http, staff):
    secretary, doctor, patient = staff
    patient_user = await make_user("patient@example.test", Role.PATIENT, patient_id=patient.id)

    assert (await http.get("/api/appointments/doctors")).status_code == 401
    for user in (secretary, doctor, patient_user):
        response = await http.get("/api/appointments/doctors", headers=auth(user))
        assert response.status_code == 200
        assert response.json() == [
            {"id": str(doctor.id), "name": "Doctor Test", "specialty": "Cardiologie"}
        ]


async def test_doctors_list_hides_inactive_doctors_and_other_roles(http, staff):
    secretary, doctor, _ = staff
    await make_doctor("inactive@example.test", "Dermatologie")
    inactive = await User.find_one(User.email == "inactive@example.test")
    inactive.is_active = False
    await inactive.save()

    response = await http.get("/api/appointments/doctors", headers=auth(secretary))

    assert [d["id"] for d in response.json()] == [str(doctor.id)]