from fastapi import APIRouter, Depends, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import get_db
from app.modules._template.repository import NoteRepository
from app.modules._template.schemas import (
    NoteCreate,
    NoteOut,
    NoteSummary,
    NoteSummaryRequest,
    NoteUpdate,
)
from app.modules._template.service import NoteService

router = APIRouter()
PREFIX = "/api/notes"
TAGS = ["notes"]


def get_note_service(database: AsyncDatabase = Depends(get_db)) -> NoteService:
    return NoteService(NoteRepository(database))


@router.post("/", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    note: NoteCreate,
    service: NoteService = Depends(get_note_service),
) -> NoteOut:
    return await service.create(note)


@router.get("/", response_model=list[NoteOut])
async def list_notes(service: NoteService = Depends(get_note_service)) -> list[NoteOut]:
    return await service.list()


@router.post("/summarize", response_model=NoteSummary)
async def summarize_note(
    request: NoteSummaryRequest,
    service: NoteService = Depends(get_note_service),
) -> NoteSummary:
    return await service.summarize(request.content)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: str,
    service: NoteService = Depends(get_note_service),
) -> NoteOut:
    return await service.get(note_id)


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    changes: NoteUpdate,
    service: NoteService = Depends(get_note_service),
) -> NoteOut:
    return await service.update(note_id, changes)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    service: NoteService = Depends(get_note_service),
) -> Response:
    await service.delete(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
