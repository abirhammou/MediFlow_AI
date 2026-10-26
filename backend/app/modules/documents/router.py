from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentExtraction,
    DocumentOut,
    DocumentPage,
    DocumentPatientOption,
    DocumentReview,
    DocumentUpdate,
)
from app.modules.documents.service import DocumentService
from app.modules.patients.service import PatientService

router = APIRouter()
TAGS = ["documents"]

readers = require_roles(
    Role.PATIENT, Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN
)
creators = require_roles(Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN)
editors = require_roles(Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN)
archivers = require_roles(Role.DOCTOR, Role.ADMIN)
extractors = require_roles(Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN)
reviewers = require_roles(Role.DOCTOR, Role.ADMIN)


def get_document_service() -> DocumentService:
    return DocumentService()


@router.get("/patient-options", response_model=list[DocumentPatientOption])
async def document_patient_options(
    q: str | None = Query(default=None, min_length=2, max_length=100),
    patient_id: str | None = None,
    _: User = Depends(
        require_roles(Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN)
    ),
) -> list[DocumentPatientOption]:
    patients = PatientService()
    if patient_id:
        patient = await patients.get_patient(patient_id)
        return [
            DocumentPatientOption(
                id=patient.id,
                record_number=patient.record_number,
                first_name=patient.first_name,
                last_name=patient.last_name,
            )
        ]

    page = await patients.list_patients(
        q=q,
        gender=None,
        blood_type=None,
        city=None,
        page=1,
        size=8,
        sort="lastName",
    )
    return [
        DocumentPatientOption(
            id=patient.id,
            record_number=patient.record_number,
            first_name=patient.first_name,
            last_name=patient.last_name,
        )
        for patient in page.items
    ]


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


@router.post(
    "/", response_model=DocumentOut, status_code=status.HTTP_201_CREATED, include_in_schema=False
)
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
    user: User = Depends(archivers),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.delete(user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/extract", response_model=DocumentExtraction)
async def extract_document(
    document_id: str,
    user: User = Depends(extractors),
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
