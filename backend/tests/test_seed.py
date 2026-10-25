from app.modules.appointments.models import Appointment
from app.modules.auth.models import Role, User
from app.modules.faq.models import FaqEntry
from app.modules.patients.models import Patient
from scripts.seed import ACCOUNTS, APPOINTMENTS, FAQ, PATIENTS, seed
from scripts.seed_dev_patients import DEV_PATIENTS


async def counts() -> dict[str, int]:
    return {
        "users": await User.count(),
        "patients": await Patient.count(),
        "appointments": await Appointment.count(),
        "faq_entries": await FaqEntry.count(),
    }


async def test_seed_is_idempotent(db):
    first = await seed("seed-test-password")
    after_first = await counts()
    second = await seed("seed-test-password")

    assert after_first == {
        "users": len(ACCOUNTS) + 1,
        "patients": len(PATIENTS) + len(DEV_PATIENTS),
        "appointments": len(APPOINTMENTS),
        "faq_entries": len(FAQ),
    }
    assert sum(first.created.values()) == sum(after_first.values())
    assert await counts() == after_first
    assert sum(second.created.values()) == 0


async def test_seeded_accounts_can_log_in(api_client):
    await seed("seed-test-password")

    admin = await api_client.post(
        "/api/auth/login",
        data={"username": "admin@mediflow.local", "password": "seed-test-password"},
    )
    pending = await api_client.post(
        "/api/auth/login",
        data={"username": "medecin.attente@mediflow.local", "password": "seed-test-password"},
    )

    assert admin.status_code == 200 and admin.json()["role"] == "ADMIN"
    assert pending.status_code == 403


async def test_patient_account_is_linked_to_its_record(db):
    await seed("seed-test-password")

    account = await User.find_one(User.email == "patient@mediflow.local")
    record = await Patient.get(account.patient_id)

    assert account.role == Role.PATIENT
    assert (record.first_name, record.last_name) == (account.first_name, account.last_name)


async def test_seed_fills_notes_without_overwriting_edits(db):
    await seed("seed-test-password")
    edited, emptied = PATIENTS[0], PATIENTS[1]
    await Patient.find_one(Patient.national_id == edited["national_id"]).set(
        {Patient.administrative_notes: "Modifiée dans l'application."}
    )
    await Patient.find_one(Patient.national_id == emptied["national_id"]).set(
        {Patient.administrative_notes: None}
    )

    kept = await seed("seed-test-password")
    after_keep = await Patient.find_one(Patient.national_id == edited["national_id"])
    refilled = await Patient.find_one(Patient.national_id == emptied["national_id"])
    reset = await seed("seed-test-password", reset_notes=True)
    after_reset = await Patient.find_one(Patient.national_id == edited["national_id"])

    assert kept.notes_updated == 1
    assert after_keep.administrative_notes == "Modifiée dans l'application."
    assert refilled.administrative_notes == emptied["administrative_notes"]
    assert reset.notes_updated == 1
    assert after_reset.administrative_notes == edited["administrative_notes"]
