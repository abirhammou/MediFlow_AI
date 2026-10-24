from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import DashboardSummary
from app.modules.dashboard.service import DashboardService


router = APIRouter()
TAGS = ["dashboard"]
LLM_ENABLED = False


def get_dashboard_service(
    database: AsyncIOMotorDatabase = Depends(get_db),
) -> DashboardService:
    return DashboardService(DashboardRepository(database))


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    user: dict = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    return await service.summary(user)
