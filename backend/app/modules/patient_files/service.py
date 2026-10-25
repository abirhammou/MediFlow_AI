"""Patient files: upload, list, download, soft delete, filtered by category and role.

A PATIENT only reaches their own record (`owns_patient_record`); the categories a
role may not read are filtered out of every list and refused (403) on direct access.
"""

import re
import unicodedata

from beanie import PydanticObjectId
from bson.errors import InvalidId

from app.core.config import settings
from app.core.time import utcnow
from app.dependencies import owns_patient_record
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_names
from app.modules.patient_files import storage
from app.modules.patient_files.models import FileCategory, FileType, PatientFile
from app.modules.patient_files.schemas import PatientFileOut
from app.modules.patients import repository as patients

# Who may do what, per category (the frontend mirrors it in patient-permissions.ts).
FILE_ROLES: dict[FileCategory, dict[str, tuple[Role, ...]]] = {
    FileCategory.ADMINISTRATIVE: {
        "read": (Role.SECRETARY, Role.ADMIN, Role.PATIENT),
        "write": (Role.SECRETARY, Role.ADMIN),
    },
    FileCategory.MEDICAL: {
        "read": (Role.DOCTOR, Role.SECRETARY, Role.ADMIN, Role.PATIENT),
        "write": (Role.SECRETARY, Role.ADMIN),
    },
}
ALL_READERS = tuple(dict.fromkeys(r for rules in FILE_ROLES.values() for r in rules["read"]))
ALL_WRITERS = tuple(dict.fromkeys(r for rules in FILE_ROLES.values() for r in rules["write"]))


def readable_categories(role: Role) -> list[FileCategory]:
    return [category for category, rules in FILE_ROLES.items() if role in rules["read"]]


def _not_found(what: str = "file") -> APIError:
    if what == "patient":
        return APIError(404, "patient_not_found", "Dossier patient introuvable.")
    return APIError(404, "file_not_found", "Document introuvable.")


def _forbidden_category(category: FileCategory) -> APIError:
    label = "administratifs" if category == FileCategory.ADMINISTRATIVE else "médicaux"
    return APIError(
        403, "file_category_forbidden", f"Les documents {label} ne vous sont pas accessibles."
    )


def _object_id(value: str, what: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError):
        raise _not_found(what) from None


def download_name(file: PatientFile) -> str:
    """ASCII file name for Content-Disposition, built from the title (never a path)."""
    ascii_title = unicodedata.normalize("NFKD", file.title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-").lower() or "document"
    return f"{slug[:80]}{storage.EXTENSIONS[file.mime]}"


class PatientFileService:
    async def _patient_id(self, user: User, patient_id: str) -> PydanticObjectId:
        owns_patient_record(user, patient_id)  # 403 for another patient's record
        patient = await patients.get_patient(_object_id(patient_id, "patient"))
        if patient is None or patient.id is None:
            raise _not_found("patient")
        return patient.id

    async def _file(self, user: User, patient_id: str, file_id: str) -> PatientFile:
        pid = await self._patient_id(user, patient_id)
        file = await PatientFile.find_one(
            {"_id": _object_id(file_id, "file"), "patientId": pid, "deletedAt": None}
        )
        if file is None:
            raise _not_found()
        if user.role not in FILE_ROLES[file.category]["read"]:
            raise _forbidden_category(file.category)
        return file

    async def _out(self, files: list[PatientFile]) -> list[PatientFileOut]:
        names = await get_user_names({f.uploaded_by for f in files if f.uploaded_by})
        return [
            PatientFileOut(
                id=str(f.id),
                patient_id=str(f.patient_id),
                category=f.category,
                file_type=f.file_type,
                title=f.title,
                original_name=f.original_name,
                mime=f.mime,
                size=f.size,
                sha256=f.sha256,
                extraction_status=f.extraction_status,
                has_text=bool(f.extracted_text),
                uploaded_by=str(f.uploaded_by) if f.uploaded_by else None,
                uploaded_by_name=names.get(f.uploaded_by) if f.uploaded_by else None,
                created_at=f.created_at,
            )
            for f in files
        ]

    async def list(
        self, user: User, patient_id: str, category: FileCategory | None
    ) -> list[PatientFileOut]:
        pid = await self._patient_id(user, patient_id)
        allowed = readable_categories(user.role)
        if category is not None:
            if category not in allowed:
                raise _forbidden_category(category)
            allowed = [category]
        files = (
            await PatientFile.find(
                {
                    "patientId": pid,
                    "category": {"$in": [c.value for c in allowed]},
                    "deletedAt": None,
                }
            )
            .sort([("createdAt", -1)])
            .to_list()
        )
        return await self._out(files)

    async def upload(
        self,
        user: User,
        patient_id: str,
        *,
        category: FileCategory,
        file_type: FileType,
        title: str,
        original_name: str | None,
        data: bytes,
    ) -> PatientFileOut:
        if user.role not in FILE_ROLES[category]["write"]:
            raise _forbidden_category(category)
        pid = await self._patient_id(user, patient_id)
        if not data:
            raise APIError(422, "file_empty", "Le fichier est vide.")
        if len(data) > storage.max_upload_bytes():
            raise APIError(
                413,
                "file_too_large",
                f"Le fichier dépasse la taille maximale ({settings.max_upload_mb} Mo).",
            )
        mime = storage.detect_mime(data)
        if mime is None:
            raise APIError(
                415, "file_type_not_allowed", "Seuls les fichiers PDF, PNG et JPEG sont acceptés."
            )

        stored = await storage.save(str(pid), data, mime)
        file = PatientFile(
            patient_id=pid,
            category=category,
            file_type=file_type,
            title=title,
            original_name=(original_name or "document")[-255:],
            storage_path=stored.path,
            mime=mime,
            size=stored.size,
            sha256=stored.sha256,
            uploaded_by=user.id,
        )
        await file.insert()
        return (await self._out([file]))[0]

    async def download(
        self, user: User, patient_id: str, file_id: str
    ) -> tuple[bytes, PatientFile]:
        file = await self._file(user, patient_id, file_id)
        try:
            data = await storage.read(file.storage_path)
        except (FileNotFoundError, storage.StorageError):
            raise APIError(
                410, "file_missing", "Le fichier n'est plus disponible sur le serveur."
            ) from None
        return data, file

    async def delete(self, user: User, patient_id: str, file_id: str) -> None:
        """Soft delete: the document disappears from the lists, the stored file is kept."""
        file = await self._file(user, patient_id, file_id)
        if user.role not in FILE_ROLES[file.category]["write"]:
            raise _forbidden_category(file.category)
        await file.set({"deletedAt": utcnow(), "updatedAt": utcnow()})
