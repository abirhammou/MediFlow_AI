"""/api/patients/{id}/history-summaries and /api/patients/{id}/chat: AI for doctors."""

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.patient_history.models import HistoryScope
from app.modules.patient_history.schemas import (
    ChatAnswer,
    ChatRequest,
    HistoryGenerate,
    HistoryReject,
    HistorySummaryOut,
    HistoryUpdate,
)
from app.modules.patient_history.service import HistorySummaryService, PatientChatService

router = APIRouter()
PREFIX = "/api/patients"
TAGS = ["patient-history"]
# Uses the shared LiteLLM client (LLM_MODEL), not a PATIENT_HISTORY_LLM_* provider.
LLM_ENABLED = False

# Who may do what (the frontend mirrors it in patient-permissions.ts).
HISTORY_ROLES: dict[str, tuple[Role, ...]] = {
    "use": (Role.DOCTOR, Role.ADMIN),  # generate, read, chat
    "review": (Role.DOCTOR,),  # edit, validate, reject
}
users = require_roles(*HISTORY_ROLES["use"])
reviewers = require_roles(*HISTORY_ROLES["review"])


def get_history_service() -> HistorySummaryService:
    return HistorySummaryService()


def get_chat_service() -> PatientChatService:
    return PatientChatService()


@router.post(
    "/{patient_id}/history-summaries/generate",
    response_model=HistorySummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_history_summary(
    patient_id: str,
    data: HistoryGenerate,
    user: User = Depends(users),
    service: HistorySummaryService = Depends(get_history_service),
) -> HistorySummaryOut:
    """New DRAFT: the whole history (TIMELINE) or one report (REPORT + reportId)."""
    return await service.generate(user, patient_id, data)


@router.get("/{patient_id}/history-summaries", response_model=list[HistorySummaryOut])
async def list_history_summaries(
    patient_id: str,
    scope: HistoryScope | None = None,
    report_id: str | None = Query(default=None, alias="reportId"),
    _: User = Depends(users),
    service: HistorySummaryService = Depends(get_history_service),
) -> list[HistorySummaryOut]:
    """Every version, newest first."""
    return await service.list(patient_id, scope, report_id)


@router.patch("/{patient_id}/history-summaries/{summary_id}", response_model=HistorySummaryOut)
async def update_history_summary(
    patient_id: str,
    summary_id: str,
    data: HistoryUpdate,
    _: User = Depends(reviewers),
    service: HistorySummaryService = Depends(get_history_service),
) -> HistorySummaryOut:
    return await service.update(patient_id, summary_id, data)


@router.post(
    "/{patient_id}/history-summaries/{summary_id}/validate", response_model=HistorySummaryOut
)
async def validate_history_summary(
    patient_id: str,
    summary_id: str,
    user: User = Depends(reviewers),
    service: HistorySummaryService = Depends(get_history_service),
) -> HistorySummaryOut:
    return await service.validate(user, patient_id, summary_id)


@router.post(
    "/{patient_id}/history-summaries/{summary_id}/reject", response_model=HistorySummaryOut
)
async def reject_history_summary(
    patient_id: str,
    summary_id: str,
    data: HistoryReject,
    user: User = Depends(reviewers),
    service: HistorySummaryService = Depends(get_history_service),
) -> HistorySummaryOut:
    return await service.reject(user, patient_id, summary_id, data)


@router.post("/{patient_id}/chat", response_model=ChatAnswer)
async def ask_patient_record(
    patient_id: str,
    data: ChatRequest,
    user: User = Depends(users),
    service: PatientChatService = Depends(get_chat_service),
) -> ChatAnswer:
    """Answer grounded only in the patient's reports, notes and medical files (not stored)."""
    return await service.ask(user, patient_id, data)
