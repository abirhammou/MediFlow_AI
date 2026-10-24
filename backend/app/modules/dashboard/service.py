from datetime import UTC, datetime, time, timedelta
from typing import Any

from app.common.roles import Role
from app.modules.dashboard.repository import (
    APPOINTMENT_DATE_FIELDS,
    DashboardRepository,
)
from app.modules.dashboard.schemas import DashboardKPI, DashboardSummary


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self.repository = repository

    async def summary(self, user: dict[str, Any]) -> DashboardSummary:
        role = user["role"]
        if role == Role.ADMIN:
            return await self._admin_summary(user)
        if role in {Role.DOCTOR, Role.SECRETARY}:
            return await self._staff_summary(user)
        return await self._patient_summary(user)

    async def _admin_summary(self, user: dict[str, Any]) -> DashboardSummary:
        total = await self.repository.count_users()
        pending = await self.repository.count_users({"status": "pending"})
        role_counts = await self.repository.count_users_by_role()
        return DashboardSummary(
            role=user["role"],
            full_name=user["full_name"],
            kpis=[
                DashboardKPI(key="total_users", label="Utilisateurs", value=total),
                DashboardKPI(key="pending_users", label="Comptes en attente", value=pending),
                DashboardKPI(key="users_by_role", label="Répartition par rôle", value=role_counts),
            ],
            alerts=[],
        )

    async def _staff_summary(self, user: dict[str, Any]) -> DashboardSummary:
        now = datetime.now(UTC)
        day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        patients = await self.repository.count_patients()
        appointments = await self.repository.count_appointments_between(day_start, day_end)
        return DashboardSummary(
            role=user["role"],
            full_name=user["full_name"],
            kpis=[
                DashboardKPI(key="patients", label="Patients", value=patients),
                DashboardKPI(
                    key="appointments_today",
                    label="Rendez-vous aujourd'hui",
                    value=appointments,
                ),
            ],
            alerts=[],
        )

    async def _patient_summary(self, user: dict[str, Any]) -> DashboardSummary:
        patient_id = user.get("patient_id")
        if patient_id is None:
            return DashboardSummary(
                role=user["role"],
                full_name=user["full_name"],
                kpis=[
                    DashboardKPI(
                        key="upcoming_appointments",
                        label="Prochains rendez-vous",
                        value=0,
                    ),
                ],
                alerts=[
                    {
                        "key": "patient_record_unlinked",
                        "message": "Dossier patient non lié, contactez l'accueil",
                    },
                ],
            )

        appointments = await self.repository.upcoming_appointments(
            patient_id,
            datetime.now(UTC),
        )
        appointments.sort(key=self._appointment_date)
        next_appointments = [
            self._appointment_summary(appointment)
            for appointment in appointments[:5]
        ]
        return DashboardSummary(
            role=user["role"],
            full_name=user["full_name"],
            kpis=[
                DashboardKPI(
                    key="upcoming_appointments",
                    label="Prochains rendez-vous",
                    value=len(appointments),
                ),
            ],
            alerts=next_appointments,
        )

    @staticmethod
    def _appointment_date(appointment: dict[str, Any]) -> datetime:
        for field in APPOINTMENT_DATE_FIELDS:
            value = appointment.get(field)
            if isinstance(value, datetime):
                return value
        return datetime.max.replace(tzinfo=UTC)

    @classmethod
    def _appointment_summary(cls, appointment: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = ("status", "reason")
        result: dict[str, Any] = {
            "key": "upcoming_appointment",
            "appointment_id": str(appointment["_id"]),
            "scheduled_at": cls._appointment_date(appointment).isoformat(),
        }
        for field in allowed_fields:
            value = appointment.get(field)
            if isinstance(value, str):
                result[field] = value
        return result
