"""Text of an uploaded MEDICAL file, for the AI history summary and the patient chat.

PDF: the embedded text (pypdf). PNG / JPEG: OCR with Tesseract (French + English),
when the binary is installed (Docker image); otherwise UNAVAILABLE. A scanned PDF
without a text layer gives EMPTY. Extraction never makes the upload fail.
"""

import io
import logging
import re
import shutil
from functools import cache

from app.modules.patient_files.models import MAX_EXTRACTED_TEXT, ExtractionStatus, FileMime

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 50
OCR_LANGUAGES = ("fra", "eng")


def clean_text(text: str) -> str:
    """Collapse the spaces of each line and drop blank lines."""
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


@cache
def ocr_languages() -> str | None:
    """Tesseract languages to use (e.g. fra+eng), or None when Tesseract is missing."""
    import pytesseract

    if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None:
        return None
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:  # broken install
        return None
    languages = [lang for lang in OCR_LANGUAGES if lang in installed]
    return "+".join(languages or sorted(installed)[:1]) or None


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])


def _image_text(data: bytes, languages: str) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return pytesseract.image_to_string(image, lang=languages)


def extract_text(data: bytes, mime: FileMime) -> tuple[str | None, ExtractionStatus]:
    try:
        if mime == FileMime.PDF:
            text = _pdf_text(data)
        else:
            languages = ocr_languages()
            if languages is None:
                return None, ExtractionStatus.UNAVAILABLE
            text = _image_text(data, languages)
    except Exception as exc:
        # The type only: the message could quote the document.
        logger.warning("Extraction du texte impossible (%s) : %s", mime.value, type(exc).__name__)
        return None, ExtractionStatus.FAILED
    text = clean_text(text)
    if not text:
        return None, ExtractionStatus.EMPTY
    return text[:MAX_EXTRACTED_TEXT], ExtractionStatus.DONE
