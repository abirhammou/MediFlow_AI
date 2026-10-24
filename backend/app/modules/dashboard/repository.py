from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GTE, LT, NE, Eq

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.auth.models import Role, User
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
