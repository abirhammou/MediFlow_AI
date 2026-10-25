"""MedDoc AI models (medical documents and their categories)."""

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import AiReviewStatus, CamelModel, MediflowDocument, TimestampedDocument

CATEGORY_CODE_PATTERN = r"^[A-Z_]+$"


class DocumentCategory(MediflowDocument):
    code: str = Field(pattern=CATEGORY_CODE_PATTERN)
    label: str
    description: str | None = None

    class Settings:
        name = "document_categories"


class ExtractedField(CamelModel):
    name: str = Field(max_length=80)
    value: str | None = None
    status: AiReviewStatus = AiReviewStatus.DRAFT
    validated_by: PydanticObjectId | None = None
    validated_at: AwareDatetime | None = None


class MedicalDocument(TimestampedDocument):
    patient_id: PydanticObjectId
    title: str = Field(max_length=200)
    raw_text: str
    file_path: str | None = None
    archived_at: AwareDatetime | None = None
    category_code: str | None = Field(
        default=None, description="validated document_categories.code"
    )
    ai_suggested_category_code: str | None = None
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    uploaded_by: PydanticObjectId | None = None

    class Settings:
        name = "medical_documents"
