"""Every Beanie model must be accepted by the strict validators of database/mongo-init.js."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from beanie import Document, PydanticObjectId
from pymongo.errors import WriteError

from app.core.db import DOCUMENT_MODELS
from app.core.models import AiReviewStatus
from app.modules.appointments.models import (
    Appointment,
    AppointmentRequest,
    AppointmentStatus,
    DayPart,
    ParsedRequest,
)
from app.modules.auth.models import (
    Availability,
    Counter,
    DoctorProfile,
    RefreshToken,
    Role,
    User,
)
from app.modules.auth.repository import get_user_by_email
from app.modules.documents.models import DocumentCategory, ExtractedField, MedicalDocument
from app.modules.faq.models import FaqEntry
from app.modules.followup.models import FollowupTask, Reminder, ReminderStatus, TaskStatus
from app.modules.llm.models import LlmInteraction, LlmModule
from app.modules.patient_files.models import (
    ExtractionStatus,
    FileCategory,
    FileMime,
    FileType,
    PatientFile,
)
from app.modules.patients.models import (
    Address,
    BloodType,
    EmergencyContact,
    Gender,
    Insurance,
    Patient,
    PatientSummary,
)
from app.modules.reports.models import MedicalReport, ReportStatus

BCRYPT_HASH = "$2b$12$" + "N" * 53
START = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)


def oid() -> PydanticObjectId:
    return PydanticObjectId()


# Minimal documents: only required fields, every optional field saved as null / default.
MINIMAL: dict[str, Callable[[], Document]] = {
    "users": lambda: User(
        email="secretariat@clinique-mediflow.tn",
        password_hash=BCRYPT_HASH,
        first_name="Salma",
        last_name="Trabelsi",
        role=Role.SECRETARY,
    ),
    "refresh_tokens": lambda: RefreshToken(
        user_id=oid(), token_hash="a" * 64, expires_at=START + timedelta(days=7)
    ),
    "counters": lambda: Counter(id="test_sequence", seq=0),
    "patients": lambda: Patient(
        record_number="PAT-2026-90001",
        first_name="Yassine",
        last_name="Ben Salah",
        date_of_birth=date(1990, 6, 1),
        gender=Gender.MALE,
    ),
    "patient_summaries": lambda: PatientSummary(patient_id=oid(), content="Patient suivi."),
    "patient_files": lambda: PatientFile(
        patient_id=oid(),
        category=FileCategory.ADMINISTRATIVE,
        file_type=FileType.INSURANCE,
        title="Attestation CNAM",
        original_name="attestation.pdf",
        storage_path="0123/abc.pdf",
        mime=FileMime.PDF,
        size=1024,
        sha256="0" * 64,
    ),
    "appointments": lambda: Appointment(
        patient_id=oid(), doctor_id=oid(), start_at=START, end_at=START + timedelta(minutes=30)
    ),
    "appointment_requests": lambda: AppointmentRequest(
        raw_message="Bonjour, je voudrais un rendez-vous la semaine prochaine."
    ),
    "medical_reports": lambda: MedicalReport(
        patient_id=oid(),
        doctor_id=oid(),
        title="Consultation de suivi",
        raw_notes="TA 12/8, pas de plainte.",
    ),
    "document_categories": lambda: DocumentCategory(code="TEST_CATEGORIE", label="Test"),
    "medical_documents": lambda: MedicalDocument(
        patient_id=oid(), title="Bilan sanguin", raw_text="Glycémie : 0,95 g/L"
    ),
    "followup_tasks": lambda: FollowupTask(description="Rappeler le patient pour ses résultats."),
    "reminders": lambda: Reminder(
        appointment_id=oid(), content="Rappel : rendez-vous demain à 9h30."
    ),
    "faq_entries": lambda: FaqEntry(
        question="Quels sont les horaires ?", answer="Du lundi au vendredi, 8h-18h."
    ),
    "llm_interactions": lambda: LlmInteraction(
        module=LlmModule.FAQ, prompt="Quels sont les horaires ?", success=False
    ),
}

# Full documents: every field of the validator is set.
FULL: dict[str, Callable[[], Document]] = {
    "users": lambda: User(
        email="dr.mansour@clinique-mediflow.tn",
        password_hash=BCRYPT_HASH,
        first_name="Karim",
        last_name="Mansour",
        role=Role.DOCTOR,
        is_active=True,
        failed_login_attempts=2,
        locked_until=START,
        last_login_at=START,
        doctor_profile=DoctorProfile(
            specialty="Cardiologie",
            phone="+216 71 000 000",
            office_room="B12",
            availabilities=[
                Availability(day_of_week=1, start_time="08:00", end_time="12:00", slot_minutes=30),
                Availability(day_of_week=3, start_time="14:00", end_time="18:30", slot_minutes=20),
            ],
        ),
    ),
    "refresh_tokens": lambda: RefreshToken(
        user_id=oid(),
        token_hash="b" * 64,
        expires_at=START + timedelta(days=7),
        revoked_at=START,
        replaced_by_token_hash="c" * 64,
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
    ),
    "counters": lambda: Counter(id="test_sequence", seq=41),
    "patients": lambda: Patient(
        record_number="PAT-2026-90002",
        first_name="Amira",
        last_name="Gharbi",
        date_of_birth=date(1985, 3, 12),
        gender=Gender.FEMALE,
        national_id="09876543",
        phone="+216 98 000 000",
        email="amira.gharbi@exemple.tn",
        address=Address(street="12 rue de la Liberté", city="Tunis", postal_code="1002"),
        blood_type=BloodType.O_NEG,
        insurance=Insurance(provider="CNAM", number="CN-123456"),
        emergency_contact=EmergencyContact(
            name="Sami Gharbi", phone="+216 22 000 000", relation="Frère"
        ),
        administrative_notes="Préfère les rendez-vous le matin.",
        current_summary_id=oid(),
        created_by=oid(),
        updated_by=oid(),
        deleted_at=None,
    ),
    "patient_summaries": lambda: PatientSummary(
        patient_id=oid(),
        content="Patiente de 41 ans, suivi cardiologique régulier.",
        status=AiReviewStatus.VALIDATED,
        llm_model="mock",
        source_snapshot={"firstName": "Amira", "dateOfBirth": START},
        generated_by=oid(),
        reviewed_by=oid(),
        reviewed_at=START,
        review_comment="Conforme.",
    ),
    "patient_files": lambda: PatientFile(
        patient_id=oid(),
        category=FileCategory.MEDICAL,
        file_type=FileType.LAB_RESULT,
        title="Bilan sanguin",
        original_name="bilan.png",
        storage_path="0123/def.png",
        mime=FileMime.PNG,
        size=52_000,
        sha256="a" * 64,
        extracted_text="Glycémie à jeun : 1,05 g/L",
        extraction_status=ExtractionStatus.DONE,
        uploaded_by=oid(),
        deleted_at=START,
    ),
    "appointments": lambda: Appointment(
        patient_id=oid(),
        doctor_id=oid(),
        start_at=START,
        end_at=START + timedelta(minutes=30),
        reason="Contrôle tension",
        status=AppointmentStatus.CANCELLED,
        cancel_reason="Empêchement du patient",
        created_by=oid(),
    ),
    "appointment_requests": lambda: AppointmentRequest(
        raw_message="Je souhaite voir le Dr Mansour mardi matin pour un contrôle.",
        parsed=ParsedRequest(
            preferred_date=START,
            day_part=DayPart.MORNING,
            doctor_id=oid(),
            specialty="Cardiologie",
            reason="Contrôle",
        ),
        patient_id=oid(),
        appointment_id=oid(),
        created_by=oid(),
    ),
    "medical_reports": lambda: MedicalReport(
        patient_id=oid(),
        doctor_id=oid(),
        appointment_id=oid(),
        title="Compte rendu de consultation",
        raw_notes="Douleur thoracique atypique, ECG normal.",
        structured_content="Motif : douleur thoracique. Examen : ECG normal.",
        status=ReportStatus.ARCHIVED,
        archived_at=START,
    ),
    "document_categories": lambda: DocumentCategory(
        code="TEST_CATEGORIE", label="Test", description="Catégorie de test"
    ),
    "medical_documents": lambda: MedicalDocument(
        patient_id=oid(),
        title="Ordonnance",
        raw_text="Paracétamol 1 g, 3 fois par jour.",
        file_path="uploads/ordonnance.pdf",
        category_code="ORDONNANCE",
        ai_suggested_category_code="ORDONNANCE",
        extracted_fields=[
            ExtractedField(
                name="medicament",
                value="Paracétamol",
                status=AiReviewStatus.VALIDATED,
                validated_by=oid(),
                validated_at=START,
            ),
            ExtractedField(name="posologie", value=None),
        ],
        uploaded_by=oid(),
    ),
    "followup_tasks": lambda: FollowupTask(
        patient_id=oid(),
        appointment_id=oid(),
        assigned_to=oid(),
        description="Envoyer les résultats d'analyse au médecin traitant.",
        due_date=START,
        status=TaskStatus.IN_PROGRESS,
        created_by=oid(),
    ),
    "reminders": lambda: Reminder(
        appointment_id=oid(),
        appointment_snapshot={"startAt": START, "doctor": "Dr Mansour"},
        content="Rappel : rendez-vous le 3 novembre à 9h30.",
        status=ReminderStatus.SENT,
        approved_by=oid(),
        sent_at=START,
    ),
    "faq_entries": lambda: FaqEntry(
        question="Faut-il être à jeun pour une prise de sang ?",
        answer="Oui, 12 heures pour un bilan lipidique.",
        category="Analyses",
        is_approved=True,
        created_by=oid(),
    ),
    "llm_interactions": lambda: LlmInteraction(
        module=LlmModule.PATIENT_RECORD,
        user_id=oid(),
        entity_id=oid(),
        prompt="Résume le dossier.",
        response="Résumé.",
        model="mock",
        tokens_in=120,
        tokens_out=40,
        latency_ms=850,
        success=True,
        error_message=None,
    ),
}

COLLECTIONS = sorted(model.Settings.name for model in DOCUMENT_MODELS)


def test_every_collection_has_a_model_and_samples():
    assert len(COLLECTIONS) == 15
    assert sorted(MINIMAL) == sorted(FULL) == COLLECTIONS


async def test_init_script_created_collections_and_indexes(db):
    assert sorted(await db.list_collection_names()) == COLLECTIONS
    patient_indexes = {index["name"] async for index in await db.patients.list_indexes()}
    assert {
        "uq_patients_record",
        "uq_patients_national_id",
        "txt_patients_search",
    } <= patient_indexes


async def test_validator_rejects_unknown_fields(db):
    with pytest.raises(WriteError) as error:
        await db.document_categories.insert_one(
            {"code": "INCONNU", "label": "Inconnu", "unknownField": True}
        )
    assert error.value.code == 121  # DocumentValidationFailure


@pytest.mark.parametrize("variant", [MINIMAL, FULL], ids=["minimal", "full"])
@pytest.mark.parametrize("collection", COLLECTIONS)
async def test_insert_and_read_back(db, collection, variant):
    document = variant[collection]()

    await document.insert()
    loaded = await type(document).get(document.id)

    assert loaded is not None
    assert loaded.model_dump() == document.model_dump()


async def test_fields_are_stored_in_camel_case_with_utc_dates(db):
    patient = FULL["patients"]()
    await patient.insert()

    raw = await db.patients.find_one({"_id": patient.id})

    assert raw["recordNumber"] == "PAT-2026-90002"
    assert raw["address"]["postalCode"] == "1002"
    assert raw["emergencyContact"]["relation"] == "Frère"
    assert "record_number" not in raw and "revision_id" not in raw
    assert raw["dateOfBirth"] == datetime(1985, 3, 12, tzinfo=UTC)
    assert raw["deletedAt"] is None
    assert raw["createdAt"] == raw["updatedAt"]


async def test_date_of_birth_is_exposed_as_a_date(db):
    patient = MINIMAL["patients"]()
    await patient.insert()

    loaded = await Patient.get(patient.id)

    assert loaded.birth_date == date(1990, 6, 1)
    assert loaded.date_of_birth.tzinfo is not None


async def test_timestamps_are_set_by_hooks(db):
    entry = MINIMAL["faq_entries"]()
    await entry.insert()
    created_at = entry.created_at

    entry.is_approved = True
    await entry.save()

    loaded = await FaqEntry.get(entry.id)
    assert loaded.created_at == created_at
    assert loaded.updated_at >= created_at


async def test_emails_are_lowercased_before_save(db):
    user = MINIMAL["users"]()
    user.email = "  Dr.Ben.Ali@Clinique-MediFlow.TN "
    await user.insert()
    patient = MINIMAL["patients"]()
    patient.email = "Yassine.BenSalah@Exemple.TN"
    await patient.insert()

    assert (await db.users.find_one({"_id": user.id}))["email"] == "dr.ben.ali@clinique-mediflow.tn"
    assert (await db.patients.find_one({"_id": patient.id}))["email"] == (
        "yassine.bensalah@exemple.tn"
    )
    found = await get_user_by_email("DR.BEN.ALI@clinique-mediflow.tn")
    assert found is not None and found.id == user.id
    assert await get_user_by_email("inconnu@clinique-mediflow.tn") is None
