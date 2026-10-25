"""API schemas of the patient files (camelCase, like the patients module)."""

from datetime import datetime

from pydantic import Field

from app.modules.patient_files.models import ExtractionStatus, FileCategory, FileMime, FileType
from app.modules.patients.schemas import OutputModel


class PatientFileOut(OutputModel):
    """The storage path and the extracted text never leave the server."""

    id: str
    patient_id: str
    category: FileCategory
    file_type: FileType = Field(alias="type")
    title: str
    original_name: str
    mime: FileMime
    size: int
    sha256: str
    extraction_status: ExtractionStatus | None
    has_text: bool
    uploaded_by: str | None
    uploaded_by_name: str | None
    created_at: datetime
