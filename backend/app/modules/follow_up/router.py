from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import get_db
from app.errors import APIError
from app.modules.follow_up.exporters import generate_docx, generate_email_html, generate_pdf
from app.modules.follow_up.repository import ReminderRepository, TaskRepository
from app.modules.follow_up.schemas import (
    ReminderDraft,
    ReminderRequest,
    ReminderStep,
    SavedReminderCreate,
    SavedReminderOut,
    SavedReminderUpdate,
    TaskCreate,
    TaskOut,
    TaskStats,
    TaskStatus,
    TaskUpdate,
)
from app.modules.follow_up.service import TaskService

router = APIRouter()
PREFIX = "/api/follow-up"
TAGS = ["follow_up"]


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
async def create_task(task: TaskCreate, service: TaskService = Depends(get_task_service)) -> TaskOut:
    """Créer une tâche de suivi."""
    return await service.create(task)


@router.get("/tasks/stats", response_model=TaskStats)
async def get_stats(service: TaskService = Depends(get_task_service)) -> TaskStats:
    """Compteurs de tâches par statut."""
    return await service.stats()


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    task_status: Optional[TaskStatus] = Query(default=None, alias="status"),
    service: TaskService = Depends(get_task_service),
) -> list[TaskOut]:
    """Lister les tâches, filtrable par statut."""
    return await service.list(task_status)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, service: TaskService = Depends(get_task_service)) -> TaskOut:
    return await service.get(task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, changes: TaskUpdate, service: TaskService = Depends(get_task_service)) -> TaskOut:
    return await service.update(task_id, changes)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, service: TaskService = Depends(get_task_service)) -> Response:
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


# ── Rappels sauvegardés — CRUD ────────────────────────────────────────────────

@router.post("/reminders", response_model=SavedReminderOut, status_code=status.HTTP_201_CREATED)
async def save_reminder(
    payload: SavedReminderCreate,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> SavedReminderOut:
    """Sauvegarder un rappel généré (étape : draft)."""
    doc = payload.model_dump()
    doc["appointment_date"] = doc["appointment_date"].isoformat()
    doc["step"] = ReminderStep.draft.value
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    saved = await repo.create(doc)
    return _serialize_reminder(saved)


@router.get("/reminders", response_model=list[SavedReminderOut])
async def list_reminders(
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> list[SavedReminderOut]:
    """Lister tous les rappels sauvegardés (les plus récents en premier)."""
    docs = await repo.list()
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
    """Modifier le contenu ou avancer l'étape (draft → reviewed → approved → exported)."""
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
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> Response:
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
    """Télécharger le rappel en PDF."""
    doc = await _get_reminder_or_404(reminder_id, repo)
    pdf_bytes = generate_pdf(
        subject=doc["subject"], body=doc["body"],
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
    )
    # Marquer comme exporté
    await repo.update(reminder_id, {"step": ReminderStep.exported.value})
    filename = f"rappel_{doc['patient_name'].replace(' ', '_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reminders/{reminder_id}/export/docx")
async def export_docx(
    reminder_id: str,
    repo: ReminderRepository = Depends(get_reminder_repo),
) -> StreamingResponse:
    """Télécharger le rappel en Word (.docx)."""
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
    """Prévisualiser le rappel au format email HTML professionnel."""
    doc = await _get_reminder_or_404(reminder_id, repo)
    html = generate_email_html(
        subject=doc["subject"], body=doc["body"],
        patient_name=doc["patient_name"],
        appointment_date=doc["appointment_date"],
        appointment_reason=doc["appointment_reason"],
    )
    await repo.update(reminder_id, {"step": ReminderStep.exported.value})
    return HTMLResponse(content=html)
