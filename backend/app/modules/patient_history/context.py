"""What the AI may read about a patient: numbered sources, nothing else.

Sources are the non-archived medical reports, the administrative notes (chat only) and
the text extracted from MEDICAL files. ADMINISTRATIVE files (insurance, invoices,
bills) are never read. Every text is masked: the patient's name, emails, phone numbers
and national ids are replaced before anything leaves the server.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from beanie import PydanticObjectId

from app.llm.anonymizer import anonymize
from app.modules.auth.repository import get_user_names
from app.modules.patient_files.models import FileCategory, PatientFile
from app.modules.patients.dates import age_on, clinic_today, from_mongo_date
from app.modules.patients.models import Gender, Patient
from app.modules.reports.models import ReportStatus
from app.modules.reports.repository import ReportRepository

MAX_REPORTS = 200
GENDER_LABELS = {Gender.MALE: "homme", Gender.FEMALE: "femme", Gender.OTHER: "autre"}


class SourceKind(str, Enum):
    REPORT = "REPORT"
    FILE = "FILE"
    NOTES = "NOTES"


@dataclass(frozen=True)
class Source:
    id: str  # "S1", "S2"... in chronological order
    kind: SourceKind
    ref_id: str | None  # report / file id (None for the notes)
    label: str
    date: datetime | None
    text: str

    @property
    def fingerprint(self) -> dict[str, str | None]:
        """Saved with a summary: a different hash later means the source changed."""
        digest = hashlib.sha256(self.text.encode()).hexdigest()[:16]
        return {
            "id": self.id,
            "kind": self.kind.value,
            "refId": self.ref_id,
            "label": self.label,
            "hash": digest,
        }


def same_sources(saved: list[dict] | None, current: list[Source]) -> bool:
    """True when no source was added, removed or changed since `saved` was taken."""

    def key(fingerprint: dict) -> tuple:
        return (fingerprint.get("kind"), fingerprint.get("refId"), fingerprint.get("hash"))

    return sorted(map(key, saved or [])) == sorted(key(s.fingerprint) for s in current)


def mask_patient(text: str, patient: Patient) -> str:
    """Patient name -> [PATIENT], then emails / phones / national ids (app.llm.anonymizer)."""
    for name in {patient.first_name, patient.last_name}:
        if name and len(name) >= 2:
            text = re.sub(rf"\b{re.escape(name)}\b", "[PATIENT]", text, flags=re.IGNORECASE)
    return anonymize(text)


def patient_profile(patient: Patient) -> str:
    age = age_on(from_mongo_date(patient.date_of_birth), clinic_today())
    return f"Patient : {GENDER_LABELS[patient.gender]}, {age} ans, dossier {patient.record_number}"


def _day(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "date inconnue"


async def collect_sources(
    patient: Patient,
    *,
    report_id: PydanticObjectId | None = None,
    include_files: bool = True,
    include_notes: bool = False,
) -> list[Source]:
    """Chronological sources; with `report_id`, only that report (files and notes ignored)."""
    assert patient.id is not None
    items: list[tuple[datetime | None, SourceKind, str | None, str, str]] = []

    reports, _ = await ReportRepository().search(
        statuses=[ReportStatus.DRAFT, ReportStatus.FINAL],
        doctor_id=None,
        patient_id=patient.id,
        text=None,
        page=1,
        size=MAX_REPORTS,
    )
    if report_id is not None:
        reports = [report for report in reports if report.id == report_id]
    doctors = await get_user_names({report.doctor_id for report in reports})
    for report in reports:
        body = (
            report.structured_content or f"Notes du médecin (non structurées) :\n{report.raw_notes}"
        )
        doctor = doctors.get(report.doctor_id)
        status = "brouillon" if report.status == ReportStatus.DRAFT else "finalisé"
        label = f"Compte rendu « {report.title} » ({status}, {_day(report.created_at)}"
        label += f", Dr {doctor})" if doctor else ")"
        items.append((report.created_at, SourceKind.REPORT, str(report.id), label, body))

    if report_id is None and include_files:
        files = await PatientFile.find(
            {
                "patientId": patient.id,
                "category": FileCategory.MEDICAL.value,
                "deletedAt": None,
                "extractedText": {"$ne": None},
            }
        ).to_list()
        for file in files:
            label = f"Document médical « {file.title} » ({_day(file.created_at)})"
            items.append(
                (file.created_at, SourceKind.FILE, str(file.id), label, file.extracted_text or "")
            )

    if report_id is None and include_notes and (patient.administrative_notes or "").strip():
        items.append(
            (
                None,
                SourceKind.NOTES,
                None,
                "Notes administratives du dossier",
                patient.administrative_notes or "",
            )
        )

    # Chronological, the undated notes last; numbered once the empty texts are dropped.
    items = [item for item in items if item[4].strip()]
    items.sort(key=lambda item: (item[0] is None, item[0].timestamp() if item[0] else 0.0))
    return [
        Source(
            id=f"S{index}",
            kind=kind,
            ref_id=ref_id,
            label=label,
            date=when,
            text=mask_patient(text.strip(), patient),
        )
        for index, (when, kind, ref_id, label, text) in enumerate(items, start=1)
    ]
