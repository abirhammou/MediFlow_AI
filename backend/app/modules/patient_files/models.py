from enum import Enum

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import TimestampedDocument

MAX_EXTRACTED_TEXT = 50_000
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class FileCategory(str, Enum):
    """ADMINISTRATIVE: insurance, invoices... (never for doctors nor the LLM). MEDICAL: clinical."""

    ADMINISTRATIVE = "ADMINISTRATIVE"
    MEDICAL = "MEDICAL"


class FileType(str, Enum):
    INSURANCE = "INSURANCE"
    ACCOUNT = "ACCOUNT"
    INVOICE = "INVOICE"
    BILL = "BILL"
    SCAN = "SCAN"
    LAB_RESULT = "LAB_RESULT"
    IMAGING = "IMAGING"
    OTHER = "OTHER"


class FileMime(str, Enum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"


class ExtractionStatus(str, Enum):
    DONE = "DONE"
    EMPTY = "EMPTY"  # nothing readable (blank page, photo without text)
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"  # no OCR engine on this server


class PatientFile(TimestampedDocument):
    patient_id: PydanticObjectId
    category: FileCategory
    file_type: FileType = Field(alias="type")
    title: str = Field(min_length=1, max_length=200)
    original_name: str = Field(max_length=255)
    storage_path: str = Field(max_length=500, description="relative to FILES_DIR")
    mime: FileMime
    size: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)
    extracted_text: str | None = Field(default=None, max_length=MAX_EXTRACTED_TEXT)
    extraction_status: ExtractionStatus | None = None
    uploaded_by: PydanticObjectId | None = None
    deleted_at: AwareDatetime | None = None

    class Settings:
        name = "patient_files"
