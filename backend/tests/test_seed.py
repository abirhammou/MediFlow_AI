from collections import Counter

from app.core.time import utcnow
from app.modules.appointments.models import Appointment, AppointmentRequest, AppointmentStatus
from app.modules.auth.models import Role, User
from app.modules.documents.models import MedicalDocument
from app.modules.faq.models import FaqEntry
from app.modules.followup.models import FollowupTask, Reminder
from app.modules.llm.models import LlmInteraction
from app.modules.patients.models import Patient, PatientSummary, SummaryStatus
from app.modules.reports.guardrails import check_content
from app.modules.reports.models import MedicalReport, ReportStatus
from scripts.seed import ACCOUNTS, APPOINTMENTS, FAQ, PATIENTS, seed
from scripts.seed_clinical_data import CLINICAL_HISTORY
from scripts.seed_dev_patients import DEV_PATIENTS


async def counts(db) -> dict[str, int]:
    return {
        "users": await User.count(),
        "patients": await Patient.count(),
        "appointments": await Appointment.count(),
        "faq_entries": await FaqEntry.count(),
        "medical_reports": await MedicalReport.count(),
        "patient_summaries": await PatientSummary.count(),
        "medical_documents": await MedicalDocument.count(),
        "appointment_requests": await AppointmentRequest.count(),
        "followup_tasks": await FollowupTask.count(),
        "followup_reminders": await db["followup_reminders"].count_documents({}),
        "reminders": await Reminder.count(),
        "llm_interactions": await LlmInteraction.count(),
    }


async def test_seed_is_idempotent(db):
    first = await seed("seed-test-password")
    after_first = await counts(db)
    second = await seed("seed-test-password")

    assert after_first["users"] == len(ACCOUNTS) + 1
    assert after_first["patients"] == len(PATIENTS) + len(DEV_PATIENTS)
    assert after_first["faq_entries"] == len(FAQ)
    visits = sum(len(history.visits) for history in CLINICAL_HISTORY.values())
    assert after_first["medical_reports"] == visits
    assert after_first["appointments"] > len(APPOINTMENTS) + visits
    assert all(after_first.values())
    assert all(first.created[kind] == total for kind, total in after_first.items())
    assert await counts(db) == after_first
    assert sum(second.created.values()) == 0


async def test_every_patient_has_reports_in_every_state(db):
    await seed("seed-test-password")

    reports = await MedicalReport.find_all().to_list()
    per_patient = Counter(report.patient_id for report in reports)

    assert len(per_patient) == len(PATIENTS) + len(DEV_PATIENTS)
    assert min(per_patient.values()) >= 3
    assert {report.status for report in reports} == set(ReportStatus)
    for report in reports:
        appointment = await Appointment.get(report.appointment_id)
        assert appointment.patient_id == report.patient_id
        assert appointment.doctor_id == report.doctor_id
        assert appointment.status == AppointmentStatus.COMPLETED
        assert report.created_at < utcnow()
        if report.structured_content:
            assert check_content(report.raw_notes, report.structured_content) == []
        if report.status == ReportStatus.ARCHIVED:
            assert report.archived_at is not None


async def test_patient_account_sees_its_final_reports(api_client, token_factory):
    await seed("seed-test-password")
    account = await User.find_one(User.email == "patient@mediflow.local")

    response = await api_client.get(
        "/api/reports", headers={"Authorization": f"Bearer {token_factory(account)}"}
    )

    items = response.json()["items"]
    assert response.status_code == 200 and items
    assert {item["status"] for item in items} == {"FINAL"}
    assert {item["patient_id"] for item in items} == {str(account.patient_id)}


async def test_at_most_one_validated_summary_per_patient(db):
    await seed("seed-test-password")

    validated = Counter(
        summary.patient_id
        for summary in await PatientSummary.find(
            PatientSummary.status == SummaryStatus.VALIDATED
        ).to_list()
    )

    assert validated and max(validated.values()) == 1


async def test_follow_up_page_reads_the_seeded_data(api_client):
    await seed("seed-test-password")

    tasks = await api_client.get("/api/follow-up/tasks")
    stats = await api_client.get("/api/follow-up/tasks/stats")
    reminders = await api_client.get("/api/follow-up/reminders")

    assert tasks.status_code == 200 and len(tasks.json()) == await FollowupTask.count()
    assert stats.json()["total"] == len(tasks.json())
    assert reminders.status_code == 200 and reminders.json()


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
