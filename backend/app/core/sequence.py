from pymongo import ReturnDocument

from app.core.time import utcnow
from app.modules.auth.models import Counter

PATIENT_RECORD_SEQUENCE = "patient_record"


async def next_record_number() -> str:
    """Next patient record number, e.g. PAT-2026-00001.

    Atomic `$inc` on counters, so concurrent calls never get the same number.
    The sequence is global: the year is only a prefix and does not reset it.
    """
    counter = await Counter.get_pymongo_collection().find_one_and_update(
        {"_id": PATIENT_RECORD_SEQUENCE},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"PAT-{utcnow().year}-{counter['seq']:05d}"
