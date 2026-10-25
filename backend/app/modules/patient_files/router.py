"""/api/patients/{id}/files: scans, lab results, insurance papers of a patient record."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.dependencies import require_roles
from app.modules.auth.models import User
from app.modules.patient_files.models import FileCategory, FileType
from app.modules.patient_files.schemas import PatientFileOut
from app.modules.patient_files.service import (
    ALL_READERS,
    ALL_WRITERS,
    PatientFileService,
    download_name,
)
from app.modules.patient_files.storage import max_upload_bytes

router = APIRouter()
PREFIX = "/api/patients"
TAGS = ["patient-files"]
LLM_ENABLED = False

readers = require_roles(*ALL_READERS)
writers = require_roles(*ALL_WRITERS)


def get_file_service() -> PatientFileService:
    return PatientFileService()


@router.post(
    "/{patient_id}/files", response_model=PatientFileOut, status_code=status.HTTP_201_CREATED
)
async def upload_file(
    patient_id: str,
    file: UploadFile = File(...),
    category: FileCategory = Form(...),
    file_type: FileType = Form(..., alias="type"),
    title: str = Form(..., min_length=1, max_length=200),
    user: User = Depends(writers),
    service: PatientFileService = Depends(get_file_service),
) -> PatientFileOut:
    """PDF, PNG or JPEG, 10 MB max by default; the type is checked on the content."""
    data = await file.read(max_upload_bytes() + 1)
    return await service.upload(
        user,
        patient_id,
        category=category,
        file_type=file_type,
        title=title.strip(),
        original_name=file.filename,
        data=data,
    )


@router.get("/{patient_id}/files", response_model=list[PatientFileOut])
async def list_files(
    patient_id: str,
    category: FileCategory | None = Query(default=None),
    user: User = Depends(readers),
    service: PatientFileService = Depends(get_file_service),
) -> list[PatientFileOut]:
    """Newest first, only the categories the role may read."""
    return await service.list(user, patient_id, category)


@router.get(
    "/{patient_id}/files/{file_id}/download",
    responses={200: {"content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}}}},
)
async def download_file(
    patient_id: str,
    file_id: str,
    user: User = Depends(readers),
    service: PatientFileService = Depends(get_file_service),
) -> Response:
    data, file = await service.download(user, patient_id, file_id)
    name = download_name(file)
    return Response(
        content=data,
        media_type=file.mime.value,
        headers={
            "Content-Disposition": f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "no-store",  # medical data: no cache
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{patient_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    patient_id: str,
    file_id: str,
    user: User = Depends(writers),
    service: PatientFileService = Depends(get_file_service),
) -> Response:
    await service.delete(user, patient_id, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
