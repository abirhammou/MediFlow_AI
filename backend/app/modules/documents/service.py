from beanie import PydanticObjectId
from bson.errors import InvalidId

from app.core.models import AiReviewStatus
from app.core.time import utcnow
from app.errors import APIError
from app.llm.service import generate_json
from app.modules.auth.models import Role, User
from app.modules.documents.guardrails import validate_extracted_fields
from app.modules.documents.models import ExtractedField, MedicalDocument
from app.modules.documents.prompts import SYSTEM_PROMPT, document_prompt
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentExtraction,
    DocumentListItem,
    DocumentOut,
    DocumentPage,
    DocumentReview,
    DocumentStatus,
    DocumentUpdate,
    ExtractedFieldOut,
    ExtractedFieldProposal,
)

STAFF_ROLES = {
    Role.DOCTOR,
    Role.SECRETARY,
    Role.ADMIN,
}


def document_status(fields: list[ExtractedField]) -> AiReviewStatus:
    if any(field.status == AiReviewStatus.REJECTED for field in fields):
        return AiReviewStatus.REJECTED
    if fields and all(field.status == AiReviewStatus.VALIDATED for field in fields):
        return AiReviewStatus.VALIDATED
    return AiReviewStatus.DRAFT


def _document_status(document: MedicalDocument) -> DocumentStatus:
    if document.archived_at is not None:
        return DocumentStatus.ARCHIVED
    return DocumentStatus(document_status(document.extracted_fields).value)


def _not_found() -> APIError:
    return APIError(404, "document_not_found", "Document médical introuvable.")


def _to_list_item(document: MedicalDocument) -> DocumentListItem:
    return DocumentListItem(
        id=str(document.id),
        patient_id=str(document.patient_id),
        title=document.title,
        category_code=document.category_code,
        ai_suggested_category_code=document.ai_suggested_category_code,
        extracted_fields=[
            ExtractedFieldOut(
                name=field.name,
                value=field.value,
                status=field.status,
                validated_by=str(field.validated_by) if field.validated_by else None,
                validated_at=field.validated_at,
            )
            for field in document.extracted_fields
        ],
        status=_document_status(document),
        archived_at=document.archived_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _to_out(document: MedicalDocument) -> DocumentOut:
    return DocumentOut(
        **_to_list_item(document).model_dump(),
        raw_text=document.raw_text,
        file_path=document.file_path,
        uploaded_by=str(document.uploaded_by) if document.uploaded_by else None,
    )


class DocumentService:
    def __init__(self, repository: DocumentRepository | None = None) -> None:
        self.repository = repository or DocumentRepository()

    @staticmethod
    def _require_staff(user: User) -> None:
        if user.role not in STAFF_ROLES:
            raise APIError(403, "role_forbidden", "Rôle non autorisé.")

    async def list(
        self,
        user: User,
        *,
        patient_id: str | None,
        page: int,
        size: int,
    ) -> DocumentPage:
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                return DocumentPage(items=[], total=0, page=page, size=size)
            patient_oid = user.patient_id
            validated_only = True
        else:
            self._require_staff(user)
            validated_only = False
            patient_oid = self._parse_patient_id(patient_id) if patient_id else None

        documents, total = await self.repository.search(
            patient_id=patient_oid,
            validated_only=validated_only,
            page=page,
            size=size,
        )
        return DocumentPage(
            items=[_to_list_item(document) for document in documents],
            total=total,
            page=page,
            size=size,
        )

    async def history(
        self,
        user: User,
        *,
        patient_id: str,
        page: int,
        size: int,
    ) -> DocumentPage:
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                return DocumentPage(items=[], total=0, page=page, size=size)
            requested_patient_id = self._parse_patient_id(patient_id)
            if requested_patient_id != user.patient_id:
                return DocumentPage(items=[], total=0, page=page, size=size)
            patient_oid = user.patient_id
            validated_only = True
        else:
            self._require_staff(user)
            patient_oid = self._parse_patient_id(patient_id)
            validated_only = False

        documents, total = await self.repository.search(
            patient_id=patient_oid,
            validated_only=validated_only,
            include_archived=user.role != Role.PATIENT,
            page=page,
            size=size,
        )
        return DocumentPage(
            items=[_to_list_item(document) for document in documents],
            total=total,
            page=page,
            size=size,
        )

    async def get(self, user: User, document_id: str) -> DocumentOut:
        document_oid = self._parse_document_id(document_id)
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                raise _not_found()
            document = await self.repository.get_patient_visible(document_oid, user.patient_id)
        else:
            self._require_staff(user)
            document = await self.repository.get(document_oid)
        if document is None:
            raise _not_found()
        return _to_out(document)

    async def create(self, user: User, data: DocumentCreate) -> DocumentOut:
        self._require_staff(user)
        document = MedicalDocument(
            patient_id=data.patient_id,
            title=data.title,
            raw_text=data.raw_text,
            uploaded_by=user.id,
        )
        return _to_out(await self.repository.create(document))

    async def update(
        self, user: User, document_id: str, data: DocumentUpdate
    ) -> DocumentOut:
        if user.role not in {Role.DOCTOR, Role.ADMIN}:
            raise APIError(403, "role_forbidden", "Rôle non autorisé.")
        document = await self._get_staff_document(document_id)
        if document.archived_at is not None:
            raise APIError(409, "document_archived", "Un document archivé ne peut pas être modifié.")
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise APIError(422, "empty_update", "Aucune modification fournie.")
        if any(value is None for value in changes.values()):
            raise APIError(422, "invalid_update", "Les champs fournis ne peuvent pas être nuls.")

        content_changed = any(
            field in changes and changes[field] != getattr(document, field)
            for field in ("title", "raw_text")
        )
        for field, value in changes.items():
            setattr(document, field, value)
        if content_changed:
            document.category_code = None
            document.ai_suggested_category_code = None
            document.extracted_fields = []
        return _to_out(await self.repository.save(document))

    async def delete(self, user: User, document_id: str) -> None:
        if user.role not in {Role.DOCTOR, Role.ADMIN}:
            raise APIError(403, "role_forbidden", "Rôle non autorisé.")
        document = await self._get_staff_document(document_id)
        if document.archived_at is not None:
            raise APIError(409, "document_already_archived", "Le document est déjà archivé.")
        document.archived_at = utcnow()
        await self.repository.save(document)

    async def extract(self, user: User, document_id: str) -> DocumentExtraction:
        if user.role not in {Role.DOCTOR, Role.ADMIN}:
            raise APIError(403, "role_forbidden", "Rôle non autorisé.")
        document = await self._get_staff_document(document_id)
        self._ensure_active(document)
        if not document.raw_text.strip():
            raise APIError(422, "empty_document_text", "Le document ne contient pas de texte.")

        categories = await self.repository.list_categories()
        category_data = [
            {"code": category.code, "label": category.label, "description": category.description}
            for category in categories
        ]
        result = await generate_json(
            module="documents",
            system=SYSTEM_PROMPT,
            user=document_prompt(document.raw_text, category_data),
            output_schema=DocumentExtraction,
        )

        fields, warnings = validate_extracted_fields(document.raw_text, result.fields)
        category_codes = {category.code for category in categories}
        suggested_category = result.suggested_category_code
        if suggested_category not in category_codes:
            if suggested_category is not None:
                warnings.append("La catégorie proposée n'existe pas; elle a été ignorée.")
            suggested_category = None

        return DocumentExtraction(
            fields=fields,
            suggested_category_code=suggested_category,
            warnings=[*result.warnings, *warnings],
        )

    async def review(
        self, user: User, document_id: str, data: DocumentReview
    ) -> DocumentOut:
        if user.role not in {Role.DOCTOR, Role.ADMIN}:
            raise APIError(403, "role_forbidden", "Rôle non autorisé.")
        document = await self._get_staff_document(document_id)
        self._ensure_active(document)

        reviewed_fields = [
            ExtractedField(name=field.name, value=field.value)
            for field in data.fields
        ]
        _, warnings = validate_extracted_fields(
            document.raw_text,
            [
                ExtractedFieldProposal(name=field.name, value=field.value)
                for field in reviewed_fields
            ],
        )
        if warnings:
            raise APIError(
                422,
                "unsupported_extracted_value",
                "Une valeur à valider n'apparaît pas dans le texte source.",
            )

        categories = await self.repository.list_categories()
        category_codes = {category.code for category in categories}
        for code in (data.category_code, data.ai_suggested_category_code):
            if code is not None and code not in category_codes:
                raise APIError(422, "invalid_document_category", "Catégorie de document inconnue.")

        reviewed_at = utcnow()
        for field in reviewed_fields:
            field.status = data.status
            field.validated_by = user.id
            field.validated_at = reviewed_at
        document.extracted_fields = reviewed_fields
        document.ai_suggested_category_code = data.ai_suggested_category_code
        document.category_code = (
            data.category_code if data.status == AiReviewStatus.VALIDATED else None
        )
        return _to_out(await self.repository.save(document))

    async def _get_staff_document(self, document_id: str) -> MedicalDocument:
        document = await self.repository.get(self._parse_document_id(document_id))
        if document is None:
            raise _not_found()
        return document

    @staticmethod
    def _ensure_active(document: MedicalDocument) -> None:
        if document.archived_at is not None:
            raise APIError(409, "document_archived", "Un document archivé ne peut plus être modifié.")

    @staticmethod
    def _parse_document_id(document_id: str) -> PydanticObjectId:
        try:
            return PydanticObjectId(document_id)
        except (InvalidId, TypeError):
            raise _not_found() from None

    @staticmethod
    def _parse_patient_id(patient_id: str) -> PydanticObjectId:
        try:
            return PydanticObjectId(patient_id)
        except (InvalidId, TypeError):
            raise APIError(422, "invalid_patient_id", "Identifiant patient invalide.") from None
