"""Demo patient files (run by scripts.seed_modules): small generated PDFs, all fictitious.

Per patient: one MEDICAL PDF per clinical document of scripts.seed_clinical_data (lab
results, imaging reports, prescriptions) and two ADMINISTRATIVE ones (insurance
certificate, consultation invoice). Idempotent: a file is looked up by patient + title.
"""

import io
from collections import Counter

from beanie.operators import Eq
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.modules.auth.models import User
from app.modules.patient_files import storage
from app.modules.patient_files.extraction import extract_text
from app.modules.patient_files.models import FileCategory, FileMime, FileType, PatientFile
from app.modules.patients.models import Patient
from scripts.seed_clinical_data import History

# document_categories.code of the clinical documents -> patient file type
DOC_TYPES = {"ANALYSE": FileType.LAB_RESULT, "COMPTE_RENDU": FileType.IMAGING}


def build_pdf(title: str, lines: list[str]) -> bytes:
    """One A4 page: clinic header, title, then the text wrapped at ~90 characters."""
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4, invariant=1)  # invariant: same bytes every run
    page.setTitle(title)
    y = A4[1] - 2 * cm
    page.setFont("Helvetica-Bold", 10)
    page.drawString(2 * cm, y, "Clinique MediFlow - document de démonstration (fictif)")
    y -= 1.2 * cm
    page.setFont("Helvetica-Bold", 14)
    page.drawString(2 * cm, y, title)
    y -= 1 * cm
    page.setFont("Helvetica", 11)
    for line in lines:
        words, current = line.split(), ""
        for word in words:
            if len(current) + len(word) > 90:
                page.drawString(2 * cm, y, current)
                y -= 0.6 * cm
                current = ""
            current = f"{current} {word}".strip()
        page.drawString(2 * cm, y, current)
        y -= 0.8 * cm
    page.showPage()
    page.save()
    return buffer.getvalue()


def demo_files(
    patient: Patient, history: History
) -> list[tuple[FileCategory, FileType, str, list[str]]]:
    name = f"{patient.first_name} {patient.last_name}"
    provider = (
        patient.insurance.provider if patient.insurance and patient.insurance.provider else None
    )
    files = [
        (
            FileCategory.MEDICAL,
            DOC_TYPES.get(doc.category, FileType.SCAN),
            doc.title,
            [f"Patient : {name} ({patient.record_number})", doc.text],
        )
        for doc in history.documents
    ]
    files.append(
        (
            FileCategory.ADMINISTRATIVE,
            FileType.INSURANCE,
            f"Attestation d'assurance {provider or 'à fournir'}",
            [
                f"Assuré : {name}",
                f"Organisme : {provider or 'non renseigné'}",
                "Attestation de droits valable pour l'année en cours.",
            ],
        )
    )
    files.append(
        (
            FileCategory.ADMINISTRATIVE,
            FileType.INVOICE,
            "Facture de consultation",
            [
                f"Patient : {name}",
                "Consultation de médecine générale : 45,000 TND.",
                "Part assurance : 31,500 TND. Reste à charge : 13,500 TND. Réglé en espèces.",
            ],
        )
    )
    return files


async def seed_patient_files(
    patient: Patient,
    history: History,
    uploader: User,
    created: Counter,
    existing: Counter,
) -> None:
    for category, file_type, title, lines in demo_files(patient, history):
        found = await PatientFile.find_one(
            Eq(PatientFile.patient_id, patient.id), Eq(PatientFile.title, title)
        )
        if found is not None:
            existing["patient_files"] += 1
            continue
        data = build_pdf(title, lines)
        stored = await storage.save(str(patient.id), data, FileMime.PDF)
        text, extraction = (
            extract_text(data, FileMime.PDF) if category == FileCategory.MEDICAL else (None, None)
        )
        await PatientFile(
            patient_id=patient.id,
            category=category,
            file_type=file_type,
            title=title,
            original_name=f"{title}.pdf",
            storage_path=stored.path,
            mime=FileMime.PDF,
            size=stored.size,
            sha256=stored.sha256,
            extracted_text=text,
            extraction_status=extraction,
            uploaded_by=uploader.id,
        ).insert()
        created["patient_files"] += 1
