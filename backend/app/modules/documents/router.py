from fastapi import APIRouter

from app.errors import APIError

router = APIRouter()


@router.get("/")
async def list_documents() -> None:
    raise APIError(501, "not_implemented", "Le module documents n'est pas encore implémenté.")
