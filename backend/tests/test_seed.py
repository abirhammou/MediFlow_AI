import hashlib
from collections import Counter

from app.core.models import AiReviewStatus
from app.core.time import utcnow
from app.modules.appointments.models import Appointment, AppointmentRequest, AppointmentStatus
from app.modules.auth.models import Role, User
from app.modules.billing.models import Invoice, InvoiceStatus, Payment
from app.modules.documents.guardrails import validate_extracted_fields
from app.modules.documents.models import MedicalDocument
from app.modules.documents.schemas import DocumentCategoryCode, ExtractedFieldProposal
from app.modules.faq.models import FaqEntry
from app.modules.followup.models import FollowupTask, Reminder
from app.modules.llm.models import LlmInteraction
from app.modules.patient_files import storage
from app.modules.patient_files.models import (
    ExtractionStatus,
    FileCategory,
    FileMime,
    FileType,
    PatientFile,
)
from app.modules.patient_history.models import HistoryScope, PatientHistorySummary
from app.modules.patients.models import Patient, PatientSummary, SummaryStatus
from app.modules.reports.guardrails import check_content
from app.modules.reports.models import MedicalReport, ReportStatus
from scripts.seed import ACCOUNTS, APPOINTMENTS, FAQ, PATIENTS, seed
from scripts.seed_clinical_data import CLINICAL_HISTORY
from scripts.seed_dev_patients import DEV_PATIENTS
from scripts.seed_document_data import DOCUMENTS


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
        "patient_files": await PatientFile.count(),
        "patient_history_summaries": await PatientHistorySummary.count(),
        "invoices": await Invoice.count(),
        "payments": await Payment.count(),
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


async def test_every_patient_has_administrative_and_medical_files(db, files_dir):
    await seed("seed-test-password")

    files = await PatientFile.find_all().to_list()
    categories: dict = {}
    for file in files:
        categories.setdefault(file.patient_id, []).append(file.category)
        data = (files_dir / file.storage_path).read_bytes()
        assert storage.detect_mime(data) == file.mime
        assert hashlib.sha256(data).hexdigest() == file.sha256 and len(data) == file.size
        assert file.created_at < utcnow()
        if file.category == FileCategory.ADMINISTRATIVE:
            assert file.extracted_text is None
        elif file.mime == FileMime.PDF:  # images need Tesseract, PDFs have a text layer
            assert file.extraction_status == ExtractionStatus.DONE and file.extracted_text

    assert len(categories) == len(PATIENTS) + len(DEV_PATIENTS)
    assert all(set(found) == set(FileCategory) for found in categories.values())
    assert min(len(found) for found in categories.values()) >= 4
    assert {FileMime.PDF, FileMime.PNG, FileMime.JPEG} == {file.mime for file in files}
    imaging = {file.title for file in files if file.file_type == FileType.IMAGING}
    assert {"IRM du genou droit (images)", "Scanner cérébral (images)"} <= imaging


async def test_medical_documents_are_complete_and_pass_the_guardrail(db):
    await seed("seed-test-password")

    documents = await MedicalDocument.find_all().to_list()
    codes = {code.value for code in DocumentCategoryCode}

    assert len(documents) == sum(len(docs) for docs in DOCUMENTS.values())
    assert DOCUMENTS.keys() == CLINICAL_HISTORY.keys()
    for document in documents:
        assert document.ai_suggested_category_code in codes
        assert document.category_code in codes | {None}
        if document.category_code:  # validated: shown as VALIDATED only with fields
            assert document.extracted_fields
        assert len(document.raw_text.splitlines()) >= 8
        assert "{date}" not in document.raw_text
        proposals = [
            ExtractedFieldProposal(name=field.name, value=field.value)
            for field in document.extracted_fields
        ]
        assert validate_extracted_fields(document.raw_text, proposals)[1] == []
        statuses = {field.status for field in document.extracted_fields}
        assert statuses <= {AiReviewStatus.VALIDATED, AiReviewStatus.DRAFT}


async def test_invoices_in_every_state_with_consistent_payments(db):
    await seed("seed-test-password")

    invoices = await Invoice.find_all().to_list()
    assert {invoice.status for invoice in invoices} == set(InvoiceStatus)
    for invoice in invoices:
        paid = sum(p.amount for p in await Payment.find({"invoiceId": invoice.id}).to_list())
        assert paid == invoice.paid_amount <= invoice.patient_share
        assert invoice.total == sum(line.amount for line in invoice.lines)
        if invoice.status == InvoiceStatus.PAID:
            assert invoice.balance == 0


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


async def test_history_summaries_cite_current_sources(api_client, user_factory, token_factory):
    await seed("seed-test-password")
    doctor = await user_factory(email="history-reader@example.test", role=Role.DOCTOR)
    headers = {"Authorization": f"Bearer {token_factory(doctor)}"}

    summaries = await PatientHistorySummary.find_all().to_list()
    validated = Counter(
        (summary.patient_id, summary.scope, summary.report_id)
        for summary in summaries
        if summary.status == SummaryStatus.VALIDATED
    )
    assert {summary.status for summary in summaries} == set(SummaryStatus)
    assert {summary.scope for summary in summaries} == set(HistoryScope)
    assert max(validated.values()) == 1

    for patient_id in {patient_id for patient_id, _, _ in validated}:
        response = await api_client.get(
            f"/api/patients/{patient_id}/history-summaries", headers=headers
        )
        assert response.status_code == 200
        for item in response.json():
            if item["status"] == "VALIDATED":
                assert not item["isOutdated"] and item["sources"]
            if item["scope"] == "TIMELINE":
                assert item["content"].startswith("Chronologie\n")
                assert "\nPoints de vigilance\n" in item["content"]


async def test_follow_up_page_reads_the_seeded_data(api_client, user_factory, token_factory):
    await seed("seed-test-password")
    secretary = await user_factory(email="followup-reader@example.test", role=Role.SECRETARY)
    headers = {"Authorization": f"Bearer {token_factory(secretary)}"}

    tasks = await api_client.get("/api/follow-up/tasks", headers=headers)
    stats = await api_client.get("/api/follow-up/tasks/stats", headers=headers)
    reminders = await api_client.get("/api/follow-up/reminders", headers=headers)

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
