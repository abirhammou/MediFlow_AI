"""Local storage of the patient files under FILES_DIR.

Files are named by a random UUID inside the patient's folder: nothing the client
sends (name, extension, declared type) is ever used to build a path. The type is
detected from the first bytes, and only PDF, PNG and JPEG are accepted.
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.modules.patient_files.models import FileMime

SIGNATURES: dict[FileMime, bytes] = {
    FileMime.PDF: b"%PDF-",
    FileMime.PNG: b"\x89PNG\r\n\x1a\n",
    FileMime.JPEG: b"\xff\xd8\xff",
}
EXTENSIONS = {FileMime.PDF: ".pdf", FileMime.PNG: ".png", FileMime.JPEG: ".jpg"}


@dataclass(frozen=True)
class StoredFile:
    path: str  # relative to FILES_DIR, with forward slashes
    size: int
    sha256: str


class StorageError(Exception):
    """A stored path points outside FILES_DIR (should never happen)."""


def detect_mime(data: bytes) -> FileMime | None:
    for mime, signature in SIGNATURES.items():
        if data.startswith(signature):
            return mime
    return None


def max_upload_bytes() -> int:
    return settings.max_upload_mb * 1024 * 1024


def _root() -> Path:
    return Path(settings.files_dir).resolve()


def _absolute(relative: str) -> Path:
    root = _root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise StorageError(relative)
    return path


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def save(patient_id: str, data: bytes, mime: FileMime) -> StoredFile:
    relative = f"{patient_id}/{uuid.uuid4().hex}{EXTENSIONS[mime]}"
    await asyncio.to_thread(_write, _absolute(relative), data)
    return StoredFile(path=relative, size=len(data), sha256=hashlib.sha256(data).hexdigest())


async def read(relative: str) -> bytes:
    return await asyncio.to_thread(_absolute(relative).read_bytes)
