from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GT, LT, NE, Eq

from app.modules.appointments.models import Appointment, AppointmentStatus


async def find_overlapping_appointment(
    doctor_id: PydanticObjectId,
    start_at: datetime,
    end_at: datetime,
    exclude_id: PydanticObjectId | None = None,
) -> Appointment | None:
    """A non-cancelled appointment of this doctor overlapping [start_at, end_at), if any.

    Back-to-back appointments (one ends when the next starts) do not overlap.
    Pass `exclude_id` when rescheduling, so the appointment does not clash with itself.
    """
    filters = [
        Eq(Appointment.doctor_id, doctor_id),
        LT(Appointment.start_at, end_at),
        GT(Appointment.end_at, start_at),
        NE(Appointment.status, AppointmentStatus.CANCELLED),
    ]
    if exclude_id is not None:
        filters.append(NE(Appointment.id, exclude_id))
    return await Appointment.find_one(*filters)
