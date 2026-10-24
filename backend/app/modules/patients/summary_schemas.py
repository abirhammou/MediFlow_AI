"""API schemas of the patient summaries (same conventions as schemas.py)."""

from datetime import datetime
from typing import Annotated, Any

from app.modules.patients.models import SUMMARY_MAX_LENGTH, SummaryStatus
from app.modules.patients.schemas import Clean, InputModel, OutputModel, _max_length

MAX_COMMENT_LENGTH = 1000


class SummaryUpdate(InputModel):
    """PATCH body: the doctor's edited text (DRAFT only)."""

    content: Annotated[str, Clean, _max_length(SUMMARY_MAX_LENGTH)]


class SummaryReject(InputModel):
    comment: Annotated[str, Clean, _max_length(MAX_COMMENT_LENGTH)]


class SummaryOut(OutputModel):
    id: str
    patient_id: str
    content: str
    status: SummaryStatus
    llm_model: str | None
    prompt_version: str | None
    source_snapshot: dict[str, Any] | None
    is_outdated: bool
    generated_by: str | None
    generated_by_name: str | None
    reviewed_by: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime
