from enum import Enum

from beanie import PydanticObjectId
from pydantic import Field

from app.core.models import CreatedAtDocument


class LlmModule(str, Enum):
    APPOINTMENT = "APPOINTMENT"
    PATIENT_RECORD = "PATIENT_RECORD"
    PATIENT_HISTORY = "PATIENT_HISTORY"  # medical summaries for doctors
    PATIENT_CHAT = "PATIENT_CHAT"  # questions on a patient record
    REPORT = "REPORT"
    MEDDOC = "MEDDOC"
    FOLLOWUP = "FOLLOWUP"
    FAQ = "FAQ"


class LlmInteraction(CreatedAtDocument):
    """Log of every LLM call, whatever the module."""

    module: LlmModule
    user_id: PydanticObjectId | None = None
    entity_id: PydanticObjectId | None = Field(
        default=None, description="patient / report / document concerned"
    )
    prompt: str
    response: str | None = None
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    success: bool
    error_message: str | None = None

    class Settings:
        name = "llm_interactions"
