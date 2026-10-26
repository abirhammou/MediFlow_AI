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
        now        = utcnow()
        day_start  = utc_midnight(now.date())
        day_end    = day_start + timedelta(days=1)
        week_end   = day_start + timedelta(days=7)

        appt_today    = await repository.count_appointments_between(day_start, day_end)
        confirmed     = await repository.count_confirmed_today(day_start, day_end)
        pending_appts = await repository.count_pending_appointments()
        patients      = await repository.count_patients()
        appt_breakdown = await repository.count_appointments_by_status(day_start, week_end)
        followup      = await repository.count_followup_tasks()
        next_appts    = await repository.next_appointments_today(now, week_end, limit=5)

        alerts = []
        for appt in next_appts:
            alerts.append({
                "key":        "upcoming_appointment",
                "start_at":   appt.start_at.isoformat(),
                "status":     appt.status.value,
                "reason":     appt.reason,
            })

        return self._summary(
            user,
            kpis=[
                DashboardKPI(key="patients",          label="Patients enregistrés",       value=patients),
                DashboardKPI(key="appointments_today",label="RDV aujourd'hui",            value=appt_today),
                DashboardKPI(key="confirmed_today",   label="RDV confirmés aujourd'hui",   value=confirmed),
                DashboardKPI(key="pending_appts",     label="RDV en attente (7 jours)",    value=pending_appts),
                DashboardKPI(key="followup_pending",  label="Tâches de suivi en attente",  value=followup.get("pending", 0)),
                DashboardKPI(key="followup_done",     label="Tâches terminées",            value=followup.get("done", 0)),
                DashboardKPI(key="total_users",       label="Utilisateurs",                value=await repository.count_users()),
                DashboardKPI(key="users_by_role",     label="Répartition par rôle",        value=await repository.count_users_by_role()),
                DashboardKPI(key="appt_breakdown",    label="RDV par statut",              value=appt_breakdown),
            ],
            alerts=alerts,
        )

    async def _staff_summary(self, user: User) -> DashboardSummary:
        now       = utcnow()
        day_start = utc_midnight(now.date())
        day_end   = day_start + timedelta(days=1)

        appt_today    = await repository.count_appointments_between(day_start, day_end)
        confirmed     = await repository.count_confirmed_today(day_start, day_end)
        patients      = await repository.count_patients()
        followup      = await repository.count_followup_tasks()
        next_appts    = await repository.next_appointments_today(now, day_end, limit=3)

        alerts = [
            {
                "key":      "upcoming_appointment",
                "start_at": a.start_at.isoformat(),
                "status":   a.status.value,
                "reason":   a.reason,
            }
            for a in next_appts
        ]

        return self._summary(
            user,
            kpis=[
                DashboardKPI(key="patients",          label="Patients",                   value=patients),
                DashboardKPI(key="appointments_today",label="Rendez-vous aujourd'hui",    value=appt_today),
                DashboardKPI(key="confirmed_today",   label="Confirmés aujourd'hui",      value=confirmed),
                DashboardKPI(key="followup_pending",  label="Tâches de suivi en attente", value=followup.get("pending", 0)),
            ],
            alerts=alerts,
        )

    async def _patient_summary(self, user: User) -> DashboardSummary:
        if user.patient_id is None:
            return self._summary(
                user,
                kpis=[DashboardKPI(key="upcoming_appointments", label="Prochains rendez-vous", value=0)],
                alerts=[{"key": "patient_record_unlinked", "message": "Dossier patient non lié, contactez l'accueil"}],
            )

        appointments, total = await repository.upcoming_appointments(user.patient_id, utcnow())
        return self._summary(
            user,
            kpis=[DashboardKPI(key="upcoming_appointments", label="Prochains rendez-vous", value=total)],
            alerts=[
                {
                    "key":            "upcoming_appointment",
                    "appointment_id": str(a.id),
                    "start_at":       a.start_at.isoformat(),
                    "status":         a.status.value,
                    "reason":         a.reason,
                }
                for a in appointments
            ],
        )

    @staticmethod
    def _summary(user: User, kpis: list[DashboardKPI], alerts: list[dict] | None = None) -> DashboardSummary:
        return DashboardSummary(
            role=user.role.value,
            full_name=f"{user.first_name} {user.last_name}",
            kpis=kpis,
            alerts=alerts or [],
        )
