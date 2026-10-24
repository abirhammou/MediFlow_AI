from bson.errors import InvalidId
from bson import ObjectId

from app.errors import APIError
from app.llm.service import generate_json
from app.modules._template.prompts import SYSTEM_PROMPT, summary_prompt
from app.modules._template.repository import NoteRepository
from app.modules._template.schemas import NoteCreate, NoteOut, NoteSummary, NoteUpdate


def _serialize(document: dict) -> NoteOut:
    return NoteOut(
        id=str(document["_id"]),
        title=document["title"],
        content=document["content"],
    )


class NoteService:
    def __init__(self, repository: NoteRepository) -> None:
        self.repository = repository

    async def create(self, note: NoteCreate) -> NoteOut:
        return _serialize(await self.repository.create(note))

    async def list(self) -> list[NoteOut]:
        return [_serialize(document) for document in await self.repository.list()]

    async def get(self, note_id: str) -> NoteOut:
        document = await self._get_document(note_id)
        return _serialize(document)

    async def update(self, note_id: str, changes: NoteUpdate) -> NoteOut:
        await self._validate_id(note_id)
        document = await self.repository.update(note_id, changes)
        if document is None:
            raise APIError(404, "note_not_found", "Note introuvable.")
        return _serialize(document)

    async def delete(self, note_id: str) -> None:
        await self._validate_id(note_id)
        if not await self.repository.delete(note_id):
            raise APIError(404, "note_not_found", "Note introuvable.")

    async def summarize(self, content: str) -> NoteSummary:
        return await generate_json(
            module="template",
            system=SYSTEM_PROMPT,
            user=summary_prompt(content),
            output_schema=NoteSummary,
        )

    async def _get_document(self, note_id: str) -> dict:
        await self._validate_id(note_id)
        document = await self.repository.get(note_id)
        if document is None:
            raise APIError(404, "note_not_found", "Note introuvable.")
        return document

    @staticmethod
    async def _validate_id(note_id: str) -> None:
        try:
            ObjectId(note_id)
        except (InvalidId, TypeError):
            raise APIError(404, "note_not_found", "Note introuvable.") from None
