from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentExtraction,
    DocumentOut,
    DocumentPage,
    DocumentReview,
    DocumentUpdate,
)
from app.modules.documents.service import DocumentService

router = APIRouter()
TAGS = ["documents"]

readers = require_roles(Role.PATIENT, Role.DOCTOR, Role.SECRETARY, Role.ADMIN)
creators = require_roles(Role.DOCTOR, Role.SECRETARY, Role.ADMIN)
editors = require_roles(Role.DOCTOR, Role.ADMIN)
reviewers = require_roles(Role.DOCTOR, Role.ADMIN)


def get_document_service() -> DocumentService:
    return DocumentService()


@router.get("/", response_model=DocumentPage)
async def list_documents(
    patient_id: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(readers),
    service: DocumentService = Depends(get_document_service),
) -> DocumentPage:
    return await service.list(user, patient_id=patient_id, page=page, size=size)


@router.get("/patients/{patient_id}/history", response_model=DocumentPage)
async def patient_document_history(
    patient_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(readers),
    service: DocumentService = Depends(get_document_service),
) -> DocumentPage:
    return await service.history(user, patient_id=patient_id, page=page, size=size)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    user: User = Depends(creators),
    service: DocumentService = Depends(get_document_service),
) -> DocumentOut:
    return await service.create(user, data)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    user: User = Depends(readers),
    service: DocumentService = Depends(get_document_service),
) -> DocumentOut:
    return await service.get(user, document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: str,
    data: DocumentUpdate,
    user: User = Depends(editors),
    service: DocumentService = Depends(get_document_service),
) -> DocumentOut:
    return await service.update(user, document_id, data)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: User = Depends(editors),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.delete(user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/extract", response_model=DocumentExtraction)
async def extract_document(
    document_id: str,
    user: User = Depends(editors),
    service: DocumentService = Depends(get_document_service),
) -> DocumentExtraction:
    return await service.extract(user, document_id)


@router.post("/{document_id}/review", response_model=DocumentOut)
async def review_document(
    document_id: str,
    data: DocumentReview,
    user: User = Depends(reviewers),
    service: DocumentService = Depends(get_document_service),
) -> DocumentOut:
    return await service.review(user, document_id, data)
