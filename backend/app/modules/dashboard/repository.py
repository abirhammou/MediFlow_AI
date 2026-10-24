from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


APPOINTMENT_DATE_FIELDS = (
    "scheduled_at",
    "start_at",
    "starts_at",
    "appointment_date",
    "date",
)


class DashboardRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self.database = database

    async def count_users(self, query: dict[str, Any] | None = None) -> int:
        return await self.database["users"].count_documents(query or {})

    async def count_users_by_role(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for role in ("admin", "doctor", "secretary", "patient"):
            counts[role] = await self.count_users({"role": role})
        return counts

    async def count_patients(self) -> int:
        return await self.database["patients"].count_documents({})

    async def count_appointments_between(
        self,
        start: datetime,
        end: datetime,
    ) -> int:
        bounds = [
            {field: {"$gte": start, "$lt": end}}
            for field in APPOINTMENT_DATE_FIELDS
        ]
        return await self.database["appointments"].count_documents({"$or": bounds})

    async def upcoming_appointments(
        self,
        patient_id: str | ObjectId,
        from_date: datetime,
    ) -> list[dict[str, Any]]:
        patient_ids: list[str | ObjectId] = [str(patient_id)]
        try:
            patient_ids.append(ObjectId(str(patient_id)))
        except InvalidId:
            pass

        date_queries = [
            {field: {"$gte": from_date}}
            for field in APPOINTMENT_DATE_FIELDS
        ]
        cursor = self.database["appointments"].find(
            {
                "patient_id": {"$in": patient_ids},
                "$or": date_queries,
            },
            {
                "_id": 1,
                "patient_id": 1,
                "scheduled_at": 1,
                "start_at": 1,
                "starts_at": 1,
                "appointment_date": 1,
                "date": 1,
                "status": 1,
                "reason": 1,
            },
        )
        return await cursor.to_list(length=100)
