"""Base classes shared by every Beanie model.

Convention: attributes are snake_case in Python and camelCase in MongoDB
(`first_name` <-> `firstName`), through an alias generator. Construct models
with either name; queries built from fields (`Patient.first_name == ...`) use
the camelCase name. Collections, fields and indexes are owned by
database/mongo-init.js: a field missing from its validator makes writes fail.
"""

from enum import Enum

from beanie import Document, Insert, Replace, Save, before_event
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.time import utcnow


def _document_alias(name: str) -> str:
    return "_id" if name == "id" else to_camel(name)


class CamelModel(BaseModel):
    """Embedded sub-document."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MediflowDocument(Document):
    model_config = ConfigDict(alias_generator=_document_alias, populate_by_name=True)


class CreatedAtDocument(MediflowDocument):
    """Collections whose validator only has `createdAt` (append-only records)."""

    created_at: AwareDatetime = Field(default_factory=utcnow)

    @before_event(Insert)
    def _stamp_insert(self) -> None:
        self.created_at = utcnow()


class TimestampedDocument(CreatedAtDocument):
    """Collections with `createdAt` and `updatedAt`.

    Hooks run on insert(), replace() and save(). insert_many() and partial
    updates (set(), update()) bypass them: set `updated_at` yourself there.
    """

    updated_at: AwareDatetime = Field(default_factory=utcnow)

    @before_event(Insert)
    def _stamp_insert(self) -> None:
        self.created_at = self.updated_at = utcnow()

    @before_event(Replace, Save)
    def _stamp_update(self) -> None:
        self.updated_at = utcnow()


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AiReviewStatus(str, Enum):
    """Review state of an AI output (patient summaries, MedDoc extracted fields)."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
