from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class UsersRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self.users = database["users"]

    async def ensure_email_index(self) -> None:
        await self.users.create_index("email", unique=True, name="email_unique")

    async def list_users(
        self,
        filters: dict[str, str],
        skip: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query = filters or {}
        cursor = self.users.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        total = await self.users.count_documents(query)
        return items, total

    async def get_by_id(self, user_id: ObjectId) -> dict[str, Any] | None:
        return await self.users.find_one({"_id": user_id})

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: str,
    ) -> dict[str, Any]:
        await self.ensure_email_index()
        user = {
            "email": email,
            "full_name": full_name,
            "password_hash": password_hash,
            "role": role,
            "status": "active",
            "patient_id": None,
            "created_at": datetime.now(UTC),
        }
        result = await self.users.insert_one(user)
        user["_id"] = result.inserted_id
        return user

    async def update_fields(
        self,
        user_id: ObjectId,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        await self.users.update_one({"_id": user_id}, {"$set": fields})
        return await self.get_by_id(user_id)

    async def update_if_status(
        self,
        user_id: ObjectId,
        expected_status: str,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = await self.users.update_one(
            {"_id": user_id, "status": expected_status},
            {"$set": fields},
        )
        if result.matched_count == 0:
            return None
        return await self.get_by_id(user_id)

    async def count_active_admins(self) -> int:
        return await self.users.count_documents(
            {"role": "admin", "status": "active"},
        )
