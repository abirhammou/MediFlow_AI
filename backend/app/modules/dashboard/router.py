from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.dashboard.schemas import DashboardSummary
from app.modules.dashboard.service import DashboardService

router = APIRouter()
TAGS = ["dashboard"]
LLM_ENABLED = False


def get_dashboard_service() -> DashboardService:
    return DashboardService()


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    user: User = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    return await service.summary(user)
