from fastapi import APIRouter, Depends, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.modules.follow_up.repository import TaskRepository
from app.modules.follow_up.schemas import (
    ReminderDraft,
    ReminderRequest,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.modules.follow_up.service import TaskService

router = APIRouter()
PREFIX = "/api/follow-up"
TAGS = ["follow_up"]


def get_task_service(database: AsyncIOMotorDatabase = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepository(database))


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """Créer une tâche de suivi."""
    return await service.create(task)


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    service: TaskService = Depends(get_task_service),
) -> list[TaskOut]:
    """Consulter toutes les tâches de suivi, triées par échéance."""
    return await service.list()


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """Consulter le détail d'une tâche."""
    return await service.get(task_id)


@router.put("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    changes: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """Modifier la description, l'échéance ou le statut d'une tâche."""
    return await service.update(task_id, changes)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> Response:
    """Supprimer une tâche de suivi."""
    await service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── LLM ───────────────────────────────────────────────────────────────────────

@router.post("/reminders/generate", response_model=ReminderDraft)
async def generate_reminder(
    request: ReminderRequest,
    service: TaskService = Depends(get_task_service),
) -> ReminderDraft:
    """
    Génère un brouillon de rappel administratif personnalisé à partir
    des données d'un rendez-vous confirmé.

    Garde-fou : seules les données du rendez-vous confirmé sont transmises au LLM.
    Aucune information n'est inventée.
    """
    return await service.generate_reminder(request)
