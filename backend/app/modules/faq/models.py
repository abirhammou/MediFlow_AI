
from beanie import PydanticObjectId
from pydantic import Field

from app.core.models import TimestampedDocument


class FaqEntry(TimestampedDocument):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=4000)
    category: str | None = None
    is_approved: bool = Field(
        default=False,
        description="The LLM only uses approved entries",
    )
    created_by: PydanticObjectId | None = None

    class Settings:
        name = "faq_entries"
