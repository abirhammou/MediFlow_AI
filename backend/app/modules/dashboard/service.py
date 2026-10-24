from datetime import timedelta

from app.core.time import utc_midnight, utcnow
from app.modules.auth.models import Role, User
from app.modules.dashboard import repository
from app.modules.dashboard.schemas import DashboardKPI, DashboardSummary

STAFF_ROLES = {Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF}


class DashboardService:
    async def summary(self, user: User) -> DashboardSummary:
        if user.role == Role.ADMIN:
            return await self._admin_summary(user)
        if user.role in STAFF_ROLES:
            return await self._staff_summary(user)
        return await self._patient_summary(user)

    async def _admin_summary(self, user: User) -> DashboardSummary:
        return self._summary(
            user,
            kpis=[
                DashboardKPI(key="total_users", label="Utilisateurs", value=await repository.count_users()),
                DashboardKPI(
                    key="inactive_users",
                    label="Comptes inactifs ou en attente",
                    value=await repository.count_users(is_active=False),
                ),
                DashboardKPI(
                    key="users_by_role",
                    label="Répartition par rôle",
                    value=await repository.count_users_by_role(),
                ),
            ],
        )

    async def _staff_summary(self, user: User) -> DashboardSummary:
        day_start = utc_midnight(utcnow().date())
        appointments = await repository.count_appointments_between(day_start, day_start + timedelta(days=1))
        return self._summary(
            user,
            kpis=[
                DashboardKPI(key="patients", label="Patients", value=await repository.count_patients()),
                DashboardKPI(key="appointments_today", label="Rendez-vous aujourd'hui", value=appointments),
            ],
        )

    async def _patient_summary(self, user: User) -> DashboardSummary:
        if user.patient_id is None:
            return self._summary(
                user,
                kpis=[DashboardKPI(key="upcoming_appointments", label="Prochains rendez-vous", value=0)],
                alerts=[
                    {
                        "key": "patient_record_unlinked",
                        "message": "Dossier patient non lié, contactez l'accueil",
                    },
                ],
            )

        appointments, total = await repository.upcoming_appointments(user.patient_id, utcnow())
        return self._summary(
            user,
            kpis=[DashboardKPI(key="upcoming_appointments", label="Prochains rendez-vous", value=total)],
            alerts=[
                {
                    "key": "upcoming_appointment",
                    "appointment_id": str(appointment.id),
                    "start_at": appointment.start_at.isoformat(),
                    "status": appointment.status.value,
                    "reason": appointment.reason,
                }
                for appointment in appointments
            ],
        )

    @staticmethod
    def _summary(
        user: User,
        kpis: list[DashboardKPI],
        alerts: list[dict] | None = None,
    ) -> DashboardSummary:
        return DashboardSummary(
            role=user.role.value,
            full_name=f"{user.first_name} {user.last_name}",
            kpis=kpis,
            alerts=alerts or [],
        )
