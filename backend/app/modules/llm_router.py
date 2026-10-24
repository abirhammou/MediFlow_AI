from fastapi import APIRouter

from app.llm.registry import status
from app.modules.discovery import discover_module_names

router = APIRouter()


@router.get("/status")
async def llm_status() -> dict[str, dict[str, str | bool]]:
    return status(discover_module_names())
