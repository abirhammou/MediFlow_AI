import re
from typing import Any

from beanie import PydanticObjectId

from app.modules.reports.models import MedicalReport, ReportStatus


class ReportRepository:
    async def create(self, report: MedicalReport) -> MedicalReport:
        return await report.insert()

    async def get(self, report_id: PydanticObjectId) -> MedicalReport | None:
        return await MedicalReport.get(report_id)

    async def save(self, report: MedicalReport) -> MedicalReport:
        return await report.save()

    async def search(
        self,
        *,
        statuses: list[ReportStatus],
        doctor_id: PydanticObjectId | None,
        patient_id: PydanticObjectId | None,
        text: str | None,
        page: int,
        size: int,
    ) -> tuple[list[MedicalReport], int]:
        query: dict[str, Any] = {"status": {"$in": [status.value for status in statuses]}}
        if doctor_id is not None:
            query["doctorId"] = doctor_id
        if patient_id is not None:
            query["patientId"] = patient_id
        if text:
            query["title"] = {"$regex": re.escape(text), "$options": "i"}

        finder = MedicalReport.find(query)
        total = await finder.count()
        items = (
            await finder.sort([("updatedAt", -1)]).skip((page - 1) * size).limit(size).to_list()
        )
        return items, total
