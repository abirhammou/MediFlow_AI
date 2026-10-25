from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.modules.follow_up.schemas import TaskCreate, TaskStatus, TaskUpdate


class TaskRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["followup_tasks"]

    async def create(self, document: dict) -> dict[str, Any]:
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def list(self) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find().sort("due_date", 1)]

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find({"status": status}).sort("due_date", 1)]

    async def list_by_patient(self, patient_id: str) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find({"patient_id": patient_id}).sort("due_date", 1)]

    async def stats(self) -> dict[str, int]:
        total     = await self.collection.count_documents({})
        pending   = await self.collection.count_documents({"status": "pending"})
        done      = await self.collection.count_documents({"status": "done"})
        cancelled = await self.collection.count_documents({"status": "cancelled"})
        return {"total": total, "pending": pending, "done": done, "cancelled": cancelled}

    async def get(self, task_id: str) -> Optional[dict[str, Any]]:
        return await self.collection.find_one({"_id": ObjectId(task_id)})

    async def update(self, task_id: str, changes: TaskUpdate) -> Optional[dict[str, Any]]:
        values = changes.model_dump(exclude_unset=True, exclude_none=True)
        if "due_date" in values:
            values["due_date"] = values["due_date"].isoformat()
        if "status" in values and hasattr(values["status"], "value"):
            values["status"] = values["status"].value
        if not values:
            return await self.get(task_id)
        await self.collection.update_one({"_id": ObjectId(task_id)}, {"$set": values})
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
