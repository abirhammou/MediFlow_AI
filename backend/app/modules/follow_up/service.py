from bson import ObjectId
from bson.errors import InvalidId

from app.errors import APIError
from app.llm.service import generate_json
from app.modules.follow_up.prompts import SYSTEM_PROMPT, reminder_prompt
from app.modules.follow_up.repository import TaskRepository
from app.modules.follow_up.schemas import (
    ReminderDraft,
    ReminderRequest,
    TaskCreate,
    TaskOut,
    TaskStatus,
    TaskUpdate,
)


def _serialize(document: dict) -> TaskOut:
    return TaskOut(
        id=str(document["_id"]),
        description=document["description"],
        due_date=document["due_date"],
        status=TaskStatus(document["status"]),
        patient_name=document["patient_name"],
        appointment_date=document["appointment_date"],
        appointment_reason=document["appointment_reason"],
    )


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(self, task: TaskCreate) -> TaskOut:
        return _serialize(await self.repository.create(task))

    async def list(self) -> list[TaskOut]:
        return [_serialize(doc) for doc in await self.repository.list()]

    async def get(self, task_id: str) -> TaskOut:
        document = await self._get_document(task_id)
        return _serialize(document)

    async def update(self, task_id: str, changes: TaskUpdate) -> TaskOut:
        await self._validate_id(task_id)
        document = await self.repository.update(task_id, changes)
        if document is None:
            raise APIError(404, "task_not_found", "Tâche introuvable.")
        return _serialize(document)

    async def delete(self, task_id: str) -> None:
        await self._validate_id(task_id)
        if not await self.repository.delete(task_id):
            raise APIError(404, "task_not_found", "Tâche introuvable.")

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def generate_reminder(self, request: ReminderRequest) -> ReminderDraft:
        """
        Génère un brouillon de rappel administratif personnalisé à partir
        des données d'un rendez-vous confirmé.
        Garde-fou : seules les données fournies dans `request` sont transmises au LLM.
        """
        return await generate_json(
            module="follow_up",
            system=SYSTEM_PROMPT,
            user=reminder_prompt(
                patient_name=request.patient_name,
                appointment_date=request.appointment_date.isoformat(),
                appointment_reason=request.appointment_reason,
            ),
            output_schema=ReminderDraft,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_document(self, task_id: str) -> dict:
        await self._validate_id(task_id)
        document = await self.repository.get(task_id)
        if document is None:
            raise APIError(404, "task_not_found", "Tâche introuvable.")
        return document

    @staticmethod
    async def _validate_id(task_id: str) -> None:
        try:
            ObjectId(task_id)
        except (InvalidId, TypeError):
            raise APIError(404, "task_not_found", "Tâche introuvable.") from None
