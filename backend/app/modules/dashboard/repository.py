from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GTE, LT, NE, Eq, In

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.auth.models import Role, User
from app.modules.followup.models import FollowupTask, TaskStatus
from app.modules.patients.models import Patient


async def count_users(*, is_active: bool | None = None) -> int:
    filters = [] if is_active is None else [Eq(User.is_active, is_active)]
    return await User.find(*filters).count()


async def count_users_by_role() -> dict[str, int]:
    return {role.value: await User.find(Eq(User.role, role)).count() for role in Role}


async def count_patients() -> int:
    return await Patient.find(Eq(Patient.deleted_at, None)).count()


async def count_appointments_between(start: datetime, end: datetime) -> int:
    return await Appointment.find(
        GTE(Appointment.start_at, start),
        LT(Appointment.start_at, end),
        NE(Appointment.status, AppointmentStatus.CANCELLED),
    ).count()


async def count_appointments_by_status(start: datetime, end: datetime) -> dict[str, int]:
    """Breakdown par statut pour la journée courante."""
    result = {}
    for s in AppointmentStatus:
        result[s.value] = await Appointment.find(
            GTE(Appointment.start_at, start),
            LT(Appointment.start_at, end),
            Eq(Appointment.status, s),
        ).count()
    return result


async def count_confirmed_today(start: datetime, end: datetime) -> int:
    return await Appointment.find(
        GTE(Appointment.start_at, start),
        LT(Appointment.start_at, end),
        Eq(Appointment.status, AppointmentStatus.CONFIRMED),
    ).count()


async def count_pending_appointments() -> int:
    return await Appointment.find(
        Eq(Appointment.status, AppointmentStatus.PENDING)
    ).count()


async def count_followup_tasks() -> dict[str, int]:
    """Follow-up tasks by API status (TODO and IN_PROGRESS both count as pending)."""
    pending = await FollowupTask.find(
        In(FollowupTask.status, [TaskStatus.TODO, TaskStatus.IN_PROGRESS])
    ).count()
    done = await FollowupTask.find(Eq(FollowupTask.status, TaskStatus.DONE)).count()
    cancelled = await FollowupTask.find(Eq(FollowupTask.status, TaskStatus.CANCELLED)).count()
    return {"pending": pending, "done": done, "cancelled": cancelled}


async def upcoming_appointments(
    patient_id: PydanticObjectId,
    from_date: datetime,
    limit: int = 5,
) -> tuple[list[Appointment], int]:
    query = Appointment.find(
        Eq(Appointment.patient_id, patient_id),
        GTE(Appointment.start_at, from_date),
        NE(Appointment.status, AppointmentStatus.CANCELLED),
    )
    total = await query.count()
    return await query.sort(+Appointment.start_at).limit(limit).to_list(), total


async def next_appointments_today(start: datetime, end: datetime, limit: int = 5) -> list[Appointment]:
    """Prochains RDV de la journée (confirmés ou en attente)."""
    return await Appointment.find(
        GTE(Appointment.start_at, start),
        LT(Appointment.start_at, end),
        NE(Appointment.status, AppointmentStatus.CANCELLED),
    ).sort(+Appointment.start_at).limit(limit).to_list()
