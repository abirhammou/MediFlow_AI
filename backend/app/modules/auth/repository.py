from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class AuthRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self.users = database["users"]

    async def ensure_email_index(self) -> None:
        await self.users.create_index("email", unique=True, name="email_unique")

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        await self.ensure_email_index()
        return await self.users.find_one({"email": email})

    async def get_by_id(self, user_id: ObjectId) -> dict[str, Any] | None:
        await self.ensure_email_index()
        return await self.users.find_one({"_id": user_id})

    async def register(
        self,
        email: str,
        full_name: str,
        password_hash: str,
        role: str,
        status: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        await self.ensure_email_index()
        user = {
            "email": email,
            "full_name": full_name,
            "password_hash": password_hash,
            "role": role,
            "status": status,
            "patient_id": None,
            "created_at": created_at,
        }
        result = await self.users.insert_one(user)
        user["_id"] = result.inserted_id
        return user

    async def update_password(self, user_id: ObjectId, password_hash: str) -> None:
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"password_hash": password_hash}},
        )
