from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.time import utc_midnight, utcnow
from app.modules.follow_up.schemas import TaskCreate, TaskStatus, TaskUpdate
from app.modules.patients.models import Patient

# followup_tasks is validated by database/mongo-init.js (camelCase fields, TASK_STATUS,
# BSON dates): the API statuses are mapped to the stored ones and back.
STORED_STATUS = {
    TaskStatus.pending: "TODO",
    TaskStatus.done: "DONE",
    TaskStatus.cancelled: "CANCELLED",
}
API_STATUS = {stored: api for api, stored in STORED_STATUS.items()} | {
    "IN_PROGRESS": TaskStatus.pending
}


def as_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


class TaskRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["followup_tasks"]

    async def create(self, task: TaskCreate, patient: Patient) -> dict[str, Any]:
        now = utcnow()
        document = {
            "description": task.description,
            "dueDate": utc_midnight(task.due_date),
            "status": STORED_STATUS[TaskStatus.pending],
            "patientId": patient.id,
            "patientName": f"{patient.first_name} {patient.last_name}",
            "patientRecordNumber": patient.record_number,
            "appointmentDate": utc_midnight(task.appointment_date),
            "appointmentReason": task.appointment_reason,
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def list(self) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find().sort("dueDate", 1)]

    async def list_by_status(self, status: TaskStatus) -> list[dict[str, Any]]:
        stored = [value for value, api in API_STATUS.items() if api == status]
        cursor = self.collection.find({"status": {"$in": stored}}).sort("dueDate", 1)
        return [doc async for doc in cursor]

    async def list_by_patient(self, patient_id: str) -> list[dict[str, Any]]:
        if not ObjectId.is_valid(patient_id):
            return []
        cursor = self.collection.find({"patientId": ObjectId(patient_id)}).sort("dueDate", 1)
        return [doc async for doc in cursor]

    async def stats(self) -> dict[str, int]:
        counts = {status.value: 0 for status in TaskStatus}
        cursor = await self.collection.aggregate(
            [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        )
        async for row in cursor:
            counts[API_STATUS[row["_id"]].value] += row["count"]
        return {"total": sum(counts.values()), **counts}

    async def get(self, task_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": ObjectId(task_id)})

    async def update(self, task_id: str, changes: TaskUpdate) -> dict[str, Any] | None:
        values = changes.model_dump(exclude_unset=True, exclude_none=True)
        stored: dict[str, Any] = {}
        if "description" in values:
            stored["description"] = values["description"]
        if "due_date" in values:
            stored["dueDate"] = utc_midnight(values["due_date"])
        if "status" in values:
            stored["status"] = STORED_STATUS[TaskStatus(values["status"])]
        if not stored:
            return await self.get(task_id)
        stored["updatedAt"] = utcnow()
        await self.collection.update_one({"_id": ObjectId(task_id)}, {"$set": stored})
        return await self.get(task_id)

    async def delete(self, task_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(task_id)})
        return result.deleted_count == 1


class ReminderRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["followup_reminders"]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return data

    async def list(self) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find().sort("created_at", -1)]

    async def get(self, reminder_id: str) -> Optional[dict[str, Any]]:
        return await self.collection.find_one({"_id": ObjectId(reminder_id)})

    async def update(self, reminder_id: str, values: dict[str, Any]) -> Optional[dict[str, Any]]:
        await self.collection.update_one({"_id": ObjectId(reminder_id)}, {"$set": values})
        return await self.get(reminder_id)

    async def delete(self, reminder_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(reminder_id)})
        return result.deleted_count == 1
