
from beanie.operators import Eq, Text

from app.modules.faq.models import FaqEntry


async def list_approved_faq(
    category: str | None = None,
) -> list[FaqEntry]:
    filters = [Eq(FaqEntry.is_approved, True)]

    if category is not None:
        filters.append(Eq(FaqEntry.category, category))

    return (
        await FaqEntry.find(*filters)
        .sort(+FaqEntry.category, +FaqEntry.question)
        .to_list()
    )


async def search_approved_faq(
    query: str,
    limit: int = 5,
) -> list[FaqEntry]:
    """Search approved FAQ entries using MongoDB text search."""
    term = query.strip()

    if not term:
        return []

    return (
        await FaqEntry.find(
            Text(term),
            Eq(FaqEntry.is_approved, True),
        )
        .sort(("score", {"$meta": "textScore"}))
        .limit(limit)
        .to_list()
    )
