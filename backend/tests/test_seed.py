from app.modules.appointments.models import Appointment
from app.modules.auth.models import Role, User
from app.modules.faq.models import FaqEntry
from app.modules.patients.models import Patient
from scripts.seed import ACCOUNTS, APPOINTMENTS, FAQ, PATIENTS, seed


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
        "patients": len(PATIENTS),
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
