from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import get_db
from app.dependencies import get_current_user
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.follow_up.exporters import generate_docx, generate_email_html, generate_pdf
from app.modules.follow_up.repository import ReminderRepository, TaskRepository
from app.modules.follow_up.schemas import (
    AdaptiveToneRequest,
    AdaptiveReminderDraft,
    LostPatientsResponse,
    NoShowPrediction,
    NoShowRequest,
    PatientSummaryRequest,
    PatientHistorySummary,
    PriorityResponse,
    ReminderDraft,
    ReminderRequest,
    ReminderStep,
    SavedReminderCreate,
    SavedReminderOut,
    SavedReminderUpdate,
    ScheduleRequest,
    ScheduleResponse,
    TaskCreate,
    TaskOut,
    TaskStats,
    TaskStatus,
    TaskUpdate,
    WeeklyReport,
    WeeklyReportRequest,
)
from app.modules.follow_up.service import TaskService

router = APIRouter()
PREFIX = "/api/follow-up"
TAGS = ["follow_up"]

STAFF_ROLES = {Role.ADMIN, Role.ADMIN_STAFF, Role.SECRETARY, Role.DOCTOR}


def get_task_service(database: AsyncDatabase = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepository(database))


def get_reminder_repo(database: AsyncDatabase = Depends(get_db)) -> ReminderRepository:
    return ReminderRepository(database)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_reminder(doc: dict) -> SavedReminderOut:
    return SavedReminderOut(
        id=str(doc["_id"]),
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
        subject=doc["subject"],
        body=doc["body"],
        step=ReminderStep(doc.get("step", "draft")),
        created_at=doc.get("created_at", ""),
    )


def _validate_oid(rid: str) -> None:
    try:
        ObjectId(rid)
    except (InvalidId, TypeError):
        raise APIError(404, "reminder_not_found", "Rappel introuvable.") from None


# ── CRUD Tasks ────────────────────────────────────────────────────────────────

@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """Créer une tâche de suivi (staff uniquement)."""
    if current_user.role not in STAFF_ROLES:
        raise APIError(403, "forbidden", "Seul le staff peut créer des tâches.")
    return await service.create(task)


@router.get("/tasks/stats", response_model=TaskStats)
async def get_stats(
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> TaskStats:
    """Compteurs de tâches par statut."""
    return await service.stats()


@router.get("/tasks/by-patient/{patient_id}", response_model=list[TaskOut])
async def list_tasks_by_patient(
    patient_id: str,
    service: TaskService = Depends(get_task_service),
) -> list[TaskOut]:
    """Lister toutes les tâches de suivi d'un patient donné."""
    return await service.list_by_patient(patient_id)


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    task_status: Optional[TaskStatus] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> list[TaskOut]:
    """
    Lister les tâches.
    - Staff : toutes les tâches, filtrables par statut.
    - Patient : uniquement ses propres tâches (filtre automatique par patient_id).
    """
    if current_user.role == Role.PATIENT:
        if current_user.patient_id is None:
            return []
        return await service.list_by_patient(str(current_user.patient_id))
    return await service.list(task_status)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, service: TaskService = Depends(get_task_service)) -> TaskOut:
    return await service.get(task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    changes: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    return await service.update(task_id, changes)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> Response:
    if current_user.role not in STAFF_ROLES:
        raise APIError(403, "forbidden", "Seul le staff peut supprimer des tâches.")
    await service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── LLM — génération ──────────────────────────────────────────────────────────

@router.post("/reminders/generate", response_model=ReminderDraft)
async def generate_reminder(
    request: ReminderRequest,
    service: TaskService = Depends(get_task_service),
) -> ReminderDraft:
    """Génère un brouillon via Gemini. Garde-fou : données du RDV uniquement."""
    return await service.generate_reminder(request)


@router.post("/tasks/prioritize", response_model=PriorityResponse)
async def prioritize_tasks(
    service: TaskService = Depends(get_task_service),
) -> PriorityResponse:
    """Gemini classe les tâches pending par priorité (HIGH/MEDIUM/LOW)."""
    return await service.prioritize_tasks()


# ── IA Avancée (staff uniquement) ─────────────────────────────────────────────

@router.post("/ai/patient-summary", response_model=PatientHistorySummary)
async def patient_history_summary(
    req: PatientSummaryRequest,
    service: TaskService = Depends(get_task_service),
) -> PatientHistorySummary:
    return await service.patient_history_summary(req)


@router.post("/ai/no-show", response_model=NoShowPrediction)
async def predict_no_show(
    req: NoShowRequest,
    service: TaskService = Depends(get_task_service),
) -> NoShowPrediction:
    return await service.predict_no_show(req)


@router.post("/ai/schedule", response_model=ScheduleResponse)
async def schedule_reminders(
    req: ScheduleRequest,
    service: TaskService = Depends(get_task_service),
) -> ScheduleResponse:
    return await service.schedule_reminders(req)


@router.post("/ai/adaptive-reminder", response_model=AdaptiveReminderDraft)
async def adaptive_reminder(
    req: AdaptiveToneRequest,
    service: TaskService = Depends(get_task_service),
) -> AdaptiveReminderDraft:
    return await service.adaptive_reminder(req)


@router.post("/ai/lost-patients", response_model=LostPatientsResponse)
async def detect_lost_patients(
    inactivity_days: int = Query(default=30, ge=7, le=365),
    service: TaskService = Depends(get_task_service),
) -> LostPatientsResponse:
    return await service.detect_lost_patients(inactivity_days)


@router.post("/ai/weekly-report", response_model=WeeklyReport)
async def weekly_report(
    req: WeeklyReportRequest,
    service: TaskService = Depends(get_task_service),
) -> WeeklyReport:
    return await service.weekly_report(req)


# ── Rappels sauvegardés ────────────────────────────────────────────────────────

@router.post("/reminders", response_model=SavedReminderOut, status_code=status.HTTP_201_CREATED)
async def save_reminder(
    payload: SavedReminderCreate,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> SavedReminderOut:
    doc = payload.model_dump()
    doc["appointment_date"] = doc["appointment_date"].isoformat()
    doc["step"] = ReminderStep.draft.value
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    saved = await repo.create(doc)
    return _serialize_reminder(saved)


@router.get("/reminders", response_model=list[SavedReminderOut])
async def list_reminders(
    current_user: User = Depends(get_current_user),
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> list[SavedReminderOut]:
    """
    Staff : tous les rappels.
    Patient : uniquement les rappels qui le concernent (filtré par patient_name).
    """
    docs = await repo.list()
    if current_user.role == Role.PATIENT:
        full_name = f"{current_user.first_name} {current_user.last_name}".strip().lower()
        docs = [
            d for d in docs
            if d.get("patient_name", "").strip().lower() == full_name
        ]
    return [_serialize_reminder(d) for d in docs]


@router.get("/reminders/{reminder_id}", response_model=SavedReminderOut)
async def get_reminder(
    reminder_id: str,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> SavedReminderOut:
    _validate_oid(reminder_id)
    doc = await repo.get(reminder_id)
    if doc is None:
        raise APIError(404, "reminder_not_found", "Rappel introuvable.")
    return _serialize_reminder(doc)


@router.patch("/reminders/{reminder_id}", response_model=SavedReminderOut)
async def update_reminder(
    reminder_id: str,
    changes: SavedReminderUpdate,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> SavedReminderOut:
    _validate_oid(reminder_id)
    values = changes.model_dump(exclude_unset=True, exclude_none=True)
    if "step" in values and hasattr(values["step"], "value"):
        values["step"] = values["step"].value
    doc = await repo.update(reminder_id, values)
    if doc is None:
        raise APIError(404, "reminder_not_found", "Rappel introuvable.")
    return _serialize_reminder(doc)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: str,
    current_user: User = Depends(get_current_user),
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> Response:
    if current_user.role not in STAFF_ROLES:
        raise APIError(403, "forbidden", "Seul le staff peut supprimer des rappels.")
    _validate_oid(reminder_id)
    if not await repo.delete(reminder_id):
        raise APIError(404, "reminder_not_found", "Rappel introuvable.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Export ────────────────────────────────────────────────────────────────────

async def _get_reminder_or_404(reminder_id: str, repo: ReminderRepository) -> dict:
    _validate_oid(reminder_id)
    doc = await repo.get(reminder_id)
    if doc is None:
        raise APIError(404, "reminder_not_found", "Rappel introuvable.")
    return doc


@router.get("/reminders/{reminder_id}/export/pdf")
async def export_pdf(
    reminder_id: str,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> StreamingResponse:
    doc = await _get_reminder_or_404(reminder_id, repo)
    pdf_bytes = generate_pdf(
        subject=doc["subject"], body=doc["body"],
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
    )
    await repo.update(reminder_id, {"step": ReminderStep.exported.value})
    filename = f"rappel_{doc['patient_name'].replace(' ', '_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reminders/{reminder_id}/export/docx")
async def export_docx(
    reminder_id: str,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> StreamingResponse:
    doc = await _get_reminder_or_404(reminder_id, repo)
    docx_bytes = generate_docx(
        subject=doc["subject"], body=doc["body"],
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
    )
    await repo.update(reminder_id, {"step": ReminderStep.exported.value})
    filename = f"rappel_{doc['patient_name'].replace(' ', '_')}.docx"
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reminders/{reminder_id}/export/email", response_class=HTMLResponse)
async def export_email(
    reminder_id: str,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> HTMLResponse:
    doc = await _get_reminder_or_404(reminder_id, repo)
    html = generate_email_html(
        subject=doc["subject"], body=doc["body"],
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
    )
    await repo.update(reminder_id, {"step": ReminderStep.exported.value})
    return HTMLResponse(content=html)
