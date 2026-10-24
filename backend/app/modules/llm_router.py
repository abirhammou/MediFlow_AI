from fastapi import APIRouter

from app.modules.discovery import discover_module_names
from app.llm.registry import status

router = APIRouter()


@router.get("/status")
async def llm_status() -> dict[str, dict[str, str | bool]]:
    return status(discover_module_names())
