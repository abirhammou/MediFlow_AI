from pymongo import ReturnDocument

from app.core.time import utcnow
from app.modules.auth.models import Counter

PATIENT_RECORD_SEQUENCE = "patient_record"
INVOICE_SEQUENCE = "invoice"
RECEIPT_SEQUENCE = "receipt"


async def next_number(sequence: str, prefix: str, width: int = 5) -> str:
    """Next number of a sequence, e.g. PAT-2026-00001 or FAC-2026-00042.

    Atomic `$inc` on counters, so concurrent calls never get the same number.
    The sequence is global: the year is only a prefix and does not reset it.
    """
    counter = await Counter.get_pymongo_collection().find_one_and_update(
        {"_id": sequence},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"{prefix}-{utcnow().year}-{counter['seq']:0{width}d}"


async def next_record_number() -> str:
    """Next patient record number, e.g. PAT-2026-00001."""
    return await next_number(PATIENT_RECORD_SEQUENCE, "PAT")
