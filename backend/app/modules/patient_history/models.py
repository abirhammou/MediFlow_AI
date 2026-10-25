from enum import Enum
from typing import Any

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import CreatedAtDocument
from app.modules.patients.models import SummaryStatus

HISTORY_MAX_LENGTH = 6000


class HistoryScope(str, Enum):
    TIMELINE = "TIMELINE"  # every report and medical file of the patient
    REPORT = "REPORT"  # one medical report


class PatientHistorySummary(CreatedAtDocument):
    """AI medical summary for doctors; every draft is kept, one VALIDATED per scope (index)."""

    patient_id: PydanticObjectId
    scope: HistoryScope
    report_id: PydanticObjectId | None = None
    content: str = Field(min_length=1, max_length=HISTORY_MAX_LENGTH)
    status: SummaryStatus = SummaryStatus.DRAFT
    llm_model: str | None = None
    source_snapshot: dict[str, Any] | None = None
    generated_by: PydanticObjectId | None = None
    reviewed_by: PydanticObjectId | None = None
    reviewed_at: AwareDatetime | None = None
    review_comment: str | None = None

    class Settings:
        name = "patient_history_summaries"
