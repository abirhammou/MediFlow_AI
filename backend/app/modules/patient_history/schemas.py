"""API schemas of the medical summaries and the patient chat (camelCase)."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.modules.patient_history.models import HISTORY_MAX_LENGTH, HistoryScope
from app.modules.patients.models import SummaryStatus
from app.modules.patients.schemas import Clean, InputModel, OutputModel, _max_length

MAX_QUESTION_LENGTH = 1000
MAX_HISTORY_TURNS = 6


class HistoryGenerate(InputModel):
    scope: HistoryScope = HistoryScope.TIMELINE
    report_id: Annotated[str | None, Clean] = None


class HistoryUpdate(InputModel):
    content: Annotated[str, Clean, _max_length(HISTORY_MAX_LENGTH)]


class HistoryReject(InputModel):
    comment: Annotated[str, Clean, _max_length(1000)]


class ChatSource(OutputModel):
    id: str  # "S1"
    kind: str  # REPORT, FILE or NOTES
    ref_id: str | None
    label: str


class HistorySummaryOut(OutputModel):
    id: str
    patient_id: str
    scope: HistoryScope
    report_id: str | None
    content: str
    status: SummaryStatus
    llm_model: str | None
    prompt_version: str | None
    sources: list[ChatSource]
    is_outdated: bool
    generated_by: str | None
    generated_by_name: str | None
    reviewed_by: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime


class ChatTurn(InputModel):
    question: Annotated[str, Clean, _max_length(MAX_QUESTION_LENGTH)]
    answer: Annotated[str, Clean, _max_length(4000)]


class ChatRequest(InputModel):
    question: Annotated[str, Clean, _max_length(MAX_QUESTION_LENGTH)]
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


class ChatAnswer(OutputModel):
    found: bool
    answer: str
    sources: list[ChatSource]
    llm_model: str | None
