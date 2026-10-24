from typing import Any

from pydantic import BaseModel


class DashboardKPI(BaseModel):
    key: str
    label: str
    value: Any


class DashboardSummary(BaseModel):
    role: str
    full_name: str
    kpis: list[DashboardKPI]
    alerts: list[dict[str, Any]]
