from typing import Any

from beanie import PydanticObjectId

from app.core.models import AiReviewStatus
from app.modules.documents.models import DocumentCategory, MedicalDocument


class DocumentRepository:
    async def create(self, document: MedicalDocument) -> MedicalDocument:
        return await document.insert()

    async def get(self, document_id: PydanticObjectId) -> MedicalDocument | None:
        return await MedicalDocument.get(document_id)

    async def get_patient_visible(
        self, document_id: PydanticObjectId, patient_id: PydanticObjectId
    ) -> MedicalDocument | None:
        return await MedicalDocument.find_one(
            {
                "_id": document_id,
                "patientId": patient_id,
                "archivedAt": None,
                **self._validated_fields_filter(),
            }
        )

    async def save(self, document: MedicalDocument) -> MedicalDocument:
        return await document.save()

    async def list_categories(self) -> list[DocumentCategory]:
        return await DocumentCategory.find().sort([("code", 1)]).to_list()

    async def get_category(self, code: str) -> DocumentCategory | None:
        return await DocumentCategory.find_one({"code": code})

    async def search(
        self,
        *,
        patient_id: PydanticObjectId | None,
        validated_only: bool,
        include_archived: bool = False,
        page: int,
        size: int,
    ) -> tuple[list[MedicalDocument], int]:
        query: dict[str, Any] = {}
        if patient_id is not None:
            query["patientId"] = patient_id
        if not include_archived:
            query["archivedAt"] = None
        if validated_only:
            query.update(self._validated_fields_filter())

        finder = MedicalDocument.find(query)
        total = await finder.count()
        items = (
            await finder.sort([("createdAt", -1), ("_id", -1)])
            .skip((page - 1) * size)
            .limit(size)
            .to_list()
        )
        return items, total

    @staticmethod
    def _validated_fields_filter() -> dict[str, Any]:
        return {
            "extractedFields.0": {"$exists": True},
            "extractedFields": {
                "$not": {
                    "$elemMatch": {
                        "status": {"$ne": AiReviewStatus.VALIDATED.value}
                    }
                }
            },
        }
