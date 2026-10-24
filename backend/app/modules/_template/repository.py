from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules._template.schemas import NoteCreate, NoteUpdate


class NoteRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self.collection = database["notes"]

    async def create(self, note: NoteCreate) -> dict[str, Any]:
        document = note.model_dump()
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def list(self) -> list[dict[str, Any]]:
        return [document async for document in self.collection.find().sort("_id", -1)]

    async def get(self, note_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": ObjectId(note_id)})

    async def update(self, note_id: str, changes: NoteUpdate) -> dict[str, Any] | None:
        values = changes.model_dump(exclude_unset=True, exclude_none=True)
        if not values:
            return await self.get(note_id)
        await self.collection.update_one({"_id": ObjectId(note_id)}, {"$set": values})
        return await self.get(note_id)

    async def delete(self, note_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(note_id)})
        return result.deleted_count == 1
