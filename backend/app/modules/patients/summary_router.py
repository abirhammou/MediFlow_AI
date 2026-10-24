"""/api/patients/{id}/summaries: AI administrative summary (included by router.py)."""

from fastapi import APIRouter, Depends, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.patients.summary_schemas import SummaryOut, SummaryReject, SummaryUpdate
from app.modules.patients.summary_service import SummaryService

router = APIRouter()

# Who may do what on summaries (the frontend mirrors it to hide buttons).
SUMMARY_ROLES: dict[str, tuple[Role, ...]] = {
    "generate": (Role.DOCTOR, Role.ADMIN),
    "history": (Role.DOCTOR, Role.ADMIN),
    "current": (Role.SECRETARY, Role.DOCTOR, Role.ADMIN),
    "review": (Role.DOCTOR,),
}
generators = require_roles(*SUMMARY_ROLES["generate"])
historians = require_roles(*SUMMARY_ROLES["history"])
readers = require_roles(*SUMMARY_ROLES["current"])
reviewers = require_roles(*SUMMARY_ROLES["review"])


def get_summary_service() -> SummaryService:
    return SummaryService()


@router.post(
    "/{patient_id}/summaries/generate",
    response_model=SummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_summary(
    patient_id: str,
    user: User = Depends(generators),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryOut:
    """New DRAFT written by the LLM; a doctor reviews it before it is used."""
    return await service.generate(patient_id, user)


@router.get("/{patient_id}/summaries", response_model=list[SummaryOut])
async def list_summaries(
    patient_id: str,
    _: User = Depends(historians),
    service: SummaryService = Depends(get_summary_service),
) -> list[SummaryOut]:
    """Every version, newest first."""
    return await service.list_summaries(patient_id)


@router.get("/{patient_id}/summaries/current", response_model=SummaryOut)
async def current_summary(
    patient_id: str,
    _: User = Depends(readers),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryOut:
    """The VALIDATED summary, or 404."""
    return await service.current(patient_id)


@router.patch("/{patient_id}/summaries/{summary_id}", response_model=SummaryOut)
async def update_summary(
    patient_id: str,
    summary_id: str,
    data: SummaryUpdate,
    _: User = Depends(reviewers),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryOut:
    """Edit the text of a DRAFT (409 otherwise)."""
    return await service.update_content(patient_id, summary_id, data)


@router.post("/{patient_id}/summaries/{summary_id}/validate", response_model=SummaryOut)
async def validate_summary(
    patient_id: str,
    summary_id: str,
    user: User = Depends(reviewers),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryOut:
    """The previous VALIDATED summary becomes SUPERSEDED."""
    return await service.validate(patient_id, summary_id, user)


@router.post("/{patient_id}/summaries/{summary_id}/reject", response_model=SummaryOut)
async def reject_summary(
    patient_id: str,
    summary_id: str,
    data: SummaryReject,
    user: User = Depends(reviewers),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryOut:
    return await service.reject(patient_id, summary_id, data, user)
