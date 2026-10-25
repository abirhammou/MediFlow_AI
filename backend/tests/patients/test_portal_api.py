"""Patient portal: clinic-created accounts, booking rules, and cross-patient isolation."""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.auth.models import Availability, DoctorProfile, Role
from app.modules.patient_portal.models import PatientAccount
from scripts.seed_files import build_pdf

EVERY_DAY = [
    Availability(day_of_week=d, start_time="08:00", end_time="18:00", slot_minutes=30)
    for d in range(1, 8)
]


@pytest.fixture
async def booking_doctor(user_factory):
    doctor = await user_factory(
        email="dr.slots@example.test", role=Role.DOCTOR, first_name="Sami", last_name="Benali"
    )
    doctor.doctor_profile = DoctorProfile(specialty="Médecine générale", availabilities=EVERY_DAY)
    await doctor.save()
    return doctor


@pytest.fixture
async def records(create_patient):
    a = await create_patient()
    b = await create_patient(
        firstName="Karim", lastName="Jaziri", nationalId="07654321", email="karim@example.test"
    )
    return a, b


@pytest.fixture
async def patients(user_factory, records):
    a, b = records
    return (
        await user_factory(email="a@portal.test", role=Role.PATIENT, patient_id=a["id"]),
        await user_factory(email="b@portal.test", role=Role.PATIENT, patient_id=b["id"]),
    )


async def first_slots(api_client, auth, user, doctor, count=1):
    response = await api_client.get(
        "/api/appointments/slots", headers=auth(user), params={"doctorId": str(doctor.id)}
    )
    assert response.status_code == 200, response.text
    return [slot["startAt"] for slot in response.json()[:count]]


async def book(api_client, auth, user, doctor, start_at, **extra):
    return await api_client.post(
        "/api/appointments",
        headers=auth(user),
        json={"doctorId": str(doctor.id), "startAt": start_at, "reason": "Contrôle", **extra},
    )


async def login(api_client, email, password):
    return await api_client.post("/api/auth/login", data={"username": email, "password": password})


# --- accounts -----------------------------------------------------------------


async def test_account_creation_and_forced_password_change(api_client, auth, secretary, records):
    a, _ = records
    url = f"/api/patients/{a['id']}/account"

    before = await api_client.get(url, headers=auth(secretary))
    created = await api_client.post(url, headers=auth(secretary), json={})
    again = await api_client.post(url, headers=auth(secretary), json={})
    temp = created.json()["temporaryPassword"]

    assert before.json() == {"exists": False} | {
        k: None
        for k in ("userId", "email", "isActive", "mustChangePassword", "lastLoginAt", "createdAt")
    }
    assert created.status_code == 201
    assert (
        created.json()["email"] == "leila.haddad@example.test"
        and created.json()["mustChangePassword"] is True
    )
    assert len(temp) == 12 and again.status_code == 409

    logged = await login(api_client, "leila.haddad@example.test", temp)
    token = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    blocked = await api_client.get("/api/portal/me", headers=token)
    me = await api_client.get("/api/auth/me", headers=token)
    same = await api_client.post(
        "/api/auth/change-password",
        headers=token,
        json={"current_password": temp, "new_password": temp},
    )
    changed = await api_client.post(
        "/api/auth/change-password",
        headers=token,
        json={"current_password": temp, "new_password": "Nouveau-mdp-2026"},
    )
    after = await api_client.get("/api/portal/me", headers=token)

    assert logged.json()["must_change_password"] is True
    assert blocked.status_code == 403 and blocked.json()["code"] == "password_change_required"
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    assert same.status_code == 400 and changed.status_code == 200
    assert after.status_code == 200 and after.json()["recordNumber"] == a["recordNumber"]
    assert "administrativeNotes" not in after.json()
    relogged = await login(api_client, "leila.haddad@example.test", "Nouveau-mdp-2026")
    assert relogged.json()["must_change_password"] is False


async def test_reset_password(api_client, auth, admin, records):
    a, _ = records
    url = f"/api/patients/{a['id']}/account"
    first = (
        await api_client.post(url, headers=auth(admin), json={"email": "leila@portal.test"})
    ).json()
    reset = await api_client.post(f"{url}/reset-password", headers=auth(admin))

    old = await login(api_client, "leila@portal.test", first["temporaryPassword"])
    new = await login(api_client, "leila@portal.test", reset.json()["temporaryPassword"])

    assert reset.status_code == 200 and reset.json()["mustChangePassword"] is True
    assert old.status_code == 401 and new.status_code == 200
    assert await PatientAccount.count() == 1


async def test_account_rules(
    api_client, auth, secretary, doctor, create_patient, records, user_factory
):
    a, b = records
    no_email = await create_patient(
        firstName="Nour", lastName="Mansouri", nationalId="05555555", email=None
    )
    await user_factory(email="karim@example.test", role=Role.SECRETARY)

    missing_email = await api_client.post(
        f"/api/patients/{no_email['id']}/account", headers=auth(secretary), json={}
    )
    taken = await api_client.post(
        f"/api/patients/{b['id']}/account", headers=auth(secretary), json={}
    )
    bad_email = await api_client.post(
        f"/api/patients/{a['id']}/account", headers=auth(secretary), json={"email": "x"}
    )
    by_doctor = await api_client.post(
        f"/api/patients/{a['id']}/account", headers=auth(doctor), json={}
    )
    reset_none = await api_client.post(
        f"/api/patients/{a['id']}/account/reset-password", headers=auth(secretary)
    )

    assert missing_email.status_code == 422 and missing_email.json()["code"] == "email_required"
    assert taken.status_code == 409 and taken.json()["code"] == "email_taken"
    assert bad_email.status_code == 422 and by_doctor.status_code == 403
    assert reset_none.status_code == 404


# --- appointments -------------------------------------------------------------


async def test_slots_follow_the_availability_grid(api_client, auth, patients, booking_doctor):
    me, _ = patients
    response = await api_client.get(
        "/api/appointments/slots", headers=auth(me), params={"doctorId": str(booking_doctor.id)}
    )
    slots = response.json()
    starts = [datetime.fromisoformat(s["startAt"]) for s in slots]

    assert slots and all(
        datetime.fromisoformat(s["endAt"]) - start == timedelta(minutes=30)
        for s, start in zip(slots, starts, strict=True)
    )
    assert starts == sorted(starts) and starts[0] > datetime.now(starts[0].tzinfo)
    doctors = (await api_client.get("/api/appointments/doctors", headers=auth(me))).json()
    assert any(d["id"] == str(booking_doctor.id) and d["availabilities"] for d in doctors)


async def test_patient_booking_flow(api_client, auth, patients, secretary, booking_doctor):
    me, other = patients
    first, second = await first_slots(api_client, auth, me, booking_doctor, 2)

    booked = await book(api_client, auth, me, booking_doctor, first)
    double = await book(api_client, auth, other, booking_doctor, first)
    off_grid = await book(
        api_client,
        auth,
        me,
        booking_doctor,
        first.replace(":00:00", ":07:00").replace(":30:00", ":07:00"),
    )
    slots_after = await first_slots(api_client, auth, me, booking_doctor, 1)
    patient_confirm = await api_client.post(
        f"/api/appointments/{booked.json()['id']}/confirm", headers=auth(me)
    )
    confirmed = await api_client.post(
        f"/api/appointments/{booked.json()['id']}/confirm", headers=auth(secretary)
    )
    cancelled = await api_client.post(
        f"/api/appointments/{booked.json()['id']}/cancel",
        headers=auth(me),
        json={"reason": "Empêchement"},
    )
    rebooked = await book(api_client, auth, other, booking_doctor, first)

    assert booked.status_code == 201 and booked.json()["status"] == "PENDING"
    assert booked.json()["doctorName"] == "Sami Benali" and booked.json()["patientName"] is None
    assert double.status_code == 409 and off_grid.status_code == 409
    assert slots_after == [second]
    assert patient_confirm.status_code == 403
    assert (
        confirmed.json()["status"] == "CONFIRMED"
        and confirmed.json()["patientName"] == "Leila Haddad"
    )
    assert (
        cancelled.json()["status"] == "CANCELLED"
        and cancelled.json()["cancelReason"] == "Empêchement"
    )
    assert rebooked.status_code == 201  # the cancelled slot is free again


async def test_concurrent_bookings_of_one_slot(api_client, auth, patients, booking_doctor):
    me, other = patients
    [slot] = await first_slots(api_client, auth, me, booking_doctor)

    results = await asyncio.gather(
        book(api_client, auth, me, booking_doctor, slot),
        book(api_client, auth, other, booking_doctor, slot),
    )

    assert sorted(r.status_code for r in results) == [201, 409]
    assert await Appointment.find({"status": {"$in": ["PENDING", "CONFIRMED"]}}).count() == 1


async def test_staff_booking_and_patient_limits(
    api_client, auth, patients, records, secretary, booking_doctor, doctor
):
    me, _ = patients
    a, _ = records
    slots = await first_slots(api_client, auth, me, booking_doctor, 5)

    no_patient = await book(api_client, auth, secretary, booking_doctor, slots[0])
    by_staff = await book(api_client, auth, secretary, booking_doctor, slots[0], patientId=a["id"])
    by_doctor = await book(api_client, auth, doctor, booking_doctor, slots[1])
    requests = [await book(api_client, auth, me, booking_doctor, s) for s in slots[1:5]]

    assert no_patient.status_code == 422
    assert by_staff.status_code == 201 and by_staff.json()["status"] == "CONFIRMED"
    assert by_doctor.status_code == 403
    assert [r.status_code for r in requests] == [201, 201, 201, 409]  # 3 pending requests at most


async def test_doctor_sees_only_their_appointments(
    api_client, auth, patients, booking_doctor, doctor
):
    me, _ = patients
    [slot] = await first_slots(api_client, auth, me, booking_doctor)
    await book(api_client, auth, me, booking_doctor, slot)

    theirs = await api_client.get("/api/appointments", headers=auth(booking_doctor))
    other = await api_client.get("/api/appointments", headers=auth(doctor))

    assert theirs.json()["total"] == 1 and other.json()["total"] == 0


# --- one patient never reads another's data -------------------------------------


@pytest.fixture
async def foreign(api_client, auth, secretary, doctor, records, patients, booking_doctor, fake_llm):
    """Data of patient B, created by staff and by B: ids to try as patient A."""
    _, b = records
    _, user_b = patients
    report = await api_client.post(
        "/api/reports",
        headers=auth(doctor),
        json={"patient_id": b["id"], "title": "CR", "raw_notes": "Notes de suivi assez longues."},
    )
    file = await api_client.post(
        f"/api/patients/{b['id']}/files",
        headers=auth(secretary),
        data={"category": "MEDICAL", "type": "SCAN", "title": "Scan"},
        files={"file": ("scan.pdf", build_pdf("Scan", ["Texte"]), "application/pdf")},
    )
    invoice = await api_client.post(
        "/api/billing/invoices",
        headers=auth(secretary),
        json={
            "patientId": b["id"],
            "lines": [{"label": "Consultation", "quantity": 1, "unitPrice": 45_000}],
        },
    )
    await api_client.post(
        f"/api/billing/invoices/{invoice.json()['id']}/issue", headers=auth(secretary)
    )
    paid = await api_client.post(
        f"/api/billing/invoices/{invoice.json()['id']}/payments",
        headers=auth(secretary),
        json={"amount": 10_000, "method": "CASH"},
    )
    [slot] = await first_slots(api_client, auth, user_b, booking_doctor)
    appointment = await book(api_client, auth, user_b, booking_doctor, slot)
    for response in (report, file, invoice, paid, appointment):
        assert response.status_code == 201, response.text  # otherwise 404s would prove nothing
    return {
        "patient": b["id"],
        "report": report.json()["id"],
        "file": file.json()["id"],
        "invoice": invoice.json()["id"],
        "payment": paid.json()["payments"][0]["id"],
        "appointment": appointment.json()["id"],
    }


FORBIDDEN_READS = [
    ("get", "/api/patients/{patient}", None),
    ("get", "/api/patients/{patient}/summaries/current", None),
    ("get", "/api/patients/{patient}/history-summaries", None),
    ("post", "/api/patients/{patient}/chat", {"question": "Résumé ?"}),
    ("get", "/api/patients/{patient}/files", None),
    ("get", "/api/patients/{patient}/files/{file}/download", None),
    ("get", "/api/patients/{patient}/account", None),
    ("get", "/api/reports/{report}", None),
    ("get", "/api/reports/{report}/pdf", None),
    ("get", "/api/billing/invoices/{invoice}", None),
    ("get", "/api/billing/invoices/{invoice}/pdf", None),
    ("get", "/api/billing/payments/{payment}/pdf", None),
    ("post", "/api/appointments/{appointment}/cancel", {"reason": "x"}),
]


@pytest.mark.parametrize(
    ("method", "path", "body"), FORBIDDEN_READS, ids=[p for _, p, _ in FORBIDDEN_READS]
)
async def test_patient_never_reaches_another_patient(
    api_client, auth, patients, foreign, method, path, body
):
    me, _ = patients
    response = await api_client.request(
        method.upper(), path.format(**foreign), headers=auth(me), **({"json": body} if body else {})
    )
    assert response.status_code in (403, 404), response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/reports?patient_id={patient}",
        "/api/billing/invoices?patientId={patient}",
        "/api/appointments?patientId={patient}",
    ],
)
async def test_patient_lists_ignore_another_patient_id(api_client, auth, patients, foreign, path):
    me, _ = patients
    response = await api_client.get(path.format(**foreign), headers=auth(me))
    assert response.status_code == 200 and response.json()["total"] == 0


async def test_booking_for_another_patient_is_refused(
    api_client, auth, patients, records, booking_doctor
):
    me, _ = patients
    _, b = records
    [slot] = await first_slots(api_client, auth, me, booking_doctor)

    spoofed = await book(api_client, auth, me, booking_doctor, slot, patientId=b["id"])

    assert spoofed.status_code == 403
    assert await Appointment.find({"patientId": {"$exists": True}}).count() == 0


async def test_portal_follow_ups_are_their_own(api_client, auth, patients, records, db):
    me, _ = patients
    a, b = records
    from app.modules.followup.models import FollowupTask, TaskStatus

    await FollowupTask(
        patient_id=a["id"], description="Prise de sang de contrôle", status=TaskStatus.TODO
    ).insert()
    await FollowupTask(
        patient_id=b["id"], description="Autre patient", status=TaskStatus.TODO
    ).insert()
    await FollowupTask(
        patient_id=a["id"], description="Annulée", status=TaskStatus.CANCELLED
    ).insert()

    response = await api_client.get("/api/portal/follow-ups", headers=auth(me))

    assert [t["description"] for t in response.json()] == ["Prise de sang de contrôle"]


async def test_portal_is_for_patients_only(api_client, auth, secretary):
    assert (await api_client.get("/api/portal/me", headers=auth(secretary))).status_code == 403


@pytest.mark.parametrize("status", [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
async def test_past_appointment_cannot_be_cancelled_by_the_patient(
    api_client, auth, patients, booking_doctor, records, status
):
    me, _ = patients
    a, _ = records
    past = datetime.now().astimezone() - timedelta(days=2)
    appointment = await Appointment(
        patient_id=a["id"],
        doctor_id=booking_doctor.id,
        start_at=past,
        end_at=past + timedelta(minutes=30),
        status=status,
    ).insert()

    response = await api_client.post(
        f"/api/appointments/{appointment.id}/cancel", headers=auth(me), json={"reason": "x"}
    )

    assert response.status_code == 409
