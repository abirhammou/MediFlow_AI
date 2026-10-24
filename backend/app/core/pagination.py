from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def check_page(page: int, page_size: int) -> int:
    """Validate pagination arguments and return the number of documents to skip."""
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return (page - 1) * page_size
