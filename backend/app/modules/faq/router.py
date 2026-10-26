
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.modules.faq.repository import (
    list_approved_faq,
    search_approved_faq,
)

router = APIRouter()
PREFIX = "/api/faq"
TAGS = ["faq"]


class FaqItem(BaseModel):
    id: str
    question: str
    answer: str
    category: str | None = None


class FaqQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class FaqAnswer(BaseModel):
    question: str
    answer: str
    found: bool
    sources: list[FaqItem]


def to_item(entry) -> FaqItem:
    return FaqItem(
        id=str(entry.id),
        question=entry.question,
        answer=entry.answer,
        category=entry.category,
    )


@router.get("", response_model=list[FaqItem])
async def get_faq(
    category: str | None = Query(default=None, max_length=100),
) -> list[FaqItem]:
    """Retourne uniquement les FAQ approuvées."""
    entries = await list_approved_faq(category)
    return [to_item(entry) for entry in entries]


@router.post("/ask", response_model=FaqAnswer)
async def ask_faq(payload: FaqQuestion) -> FaqAnswer:
    """Recherche une réponse dans les FAQ approuvées."""
    entries = await search_approved_faq(payload.question, limit=5)
    sources = [to_item(entry) for entry in entries]

    if not sources:
        return FaqAnswer(
            question=payload.question,
            answer=(
                "Je n'ai pas trouvé de réponse approuvée à cette question. "
                "Veuillez contacter directement la clinique."
            ),
            found=False,
            sources=[],
        )

    # Réponse strictement fondée sur les informations approuvées.
    answer = "\n\n".join(
        f"{item.question}\n{item.answer}" for item in sources
    )

    return FaqAnswer(
        question=payload.question,
        answer=answer,
        found=True,
        sources=sources,
    )
