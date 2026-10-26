from enum import Enum

from beanie import PydanticObjectId
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.models import AiReviewStatus, CamelModel


class DocumentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    patient_id: PydanticObjectId
    title: str = Field(min_length=1, max_length=200)
    raw_text: str = Field(min_length=1)


class DocumentPatientOption(CamelModel):
    id: str
    record_number: str
    first_name: str
    last_name: str


class DocumentStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class DocumentCategoryCode(str, Enum):
    MEDICAL = "MEDICAL"
    ORDONNANCE = "ORDONNANCE"
    CERTIFICAT = "CERTIFICAT"
    FINANCIER = "FINANCIER"
    CNAM = "CNAM"
    ADMINISTRATIF = "ADMINISTRATIF"


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    raw_text: str | None = Field(default=None, min_length=1)


class ExtractedFieldOut(BaseModel):
    name: str
    value: str | None
    status: AiReviewStatus
    validated_by: str | None
    validated_at: AwareDatetime | None


class DocumentListItem(BaseModel):
    id: str
    patient_id: str
    title: str
    category_code: str | None
    ai_suggested_category_code: str | None
    extracted_fields: list[ExtractedFieldOut]
    status: DocumentStatus
    archived_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DocumentOut(DocumentListItem):
    raw_text: str
    file_path: str | None
    uploaded_by: str | None
    validated_by_name: str | None = None


class DocumentPage(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    size: int


class ExtractedFieldProposal(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    value: str | None = Field(default=None, min_length=1)


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[ExtractedFieldProposal]
    suggested_category_code: DocumentCategoryCode | None = None
    warnings: list[str] = Field(default_factory=list)


class ReviewedField(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    value: str | None = Field(default=None, min_length=1)


class DocumentReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: AiReviewStatus
    fields: list[ReviewedField] = Field(min_length=1)
    category_code: DocumentCategoryCode | None = None
    ai_suggested_category_code: DocumentCategoryCode | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: AiReviewStatus) -> AiReviewStatus:
        if value not in (AiReviewStatus.VALIDATED, AiReviewStatus.REJECTED):
            raise ValueError("Le statut de revue doit être VALIDATED ou REJECTED.")
        return value
