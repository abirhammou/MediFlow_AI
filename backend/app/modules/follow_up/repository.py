from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.modules.follow_up.schemas import TaskCreate, TaskStatus, TaskUpdate


class TaskRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["followup_tasks"]

    async def create(self, task: TaskCreate) -> dict[str, Any]:
        document = task.model_dump()
        # dates stockées en string ISO pour MongoDB
        document["due_date"] = document["due_date"].isoformat()
        document["appointment_date"] = document["appointment_date"].isoformat()
        document["status"] = TaskStatus.pending.value
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def list(self) -> list[dict[str, Any]]:
        return [doc async for doc in self.collection.find().sort("due_date", 1)]

    async def get(self, task_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": ObjectId(task_id)})

    async def update(self, task_id: str, changes: TaskUpdate) -> dict[str, Any] | None:
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
