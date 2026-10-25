import re
from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GT, GTE, LT, NE, Eq

from app.core.pagination import Page, check_page
from app.modules.appointments.models import (
    Appointment,
    AppointmentRequest,
    AppointmentStatus,
)
from app.modules.auth.models import Role, User
from app.modules.patients.models import Patient


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


# ── Rendez-vous ───────────────────────────────────────────────────────────────


async def insert_appointment(appointment: Appointment) -> Appointment:
    return await appointment.insert()


async def get_appointment(appointment_id: PydanticObjectId) -> Appointment | None:
    return await Appointment.get(appointment_id)


async def save_appointment(appointment: Appointment) -> Appointment:
    await appointment.save()
    return appointment


async def list_appointments(
    *,
    patient_id: PydanticObjectId | None = None,
    doctor_id: PydanticObjectId | None = None,
    status: AppointmentStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[Appointment]:
    """Rendez-vous triés par date de début. `date_to` est exclu."""
    skip = check_page(page, page_size)
    filters = []
    if patient_id is not None:
        filters.append(Eq(Appointment.patient_id, patient_id))
    if doctor_id is not None:
        filters.append(Eq(Appointment.doctor_id, doctor_id))
    if status is not None:
        filters.append(Eq(Appointment.status, status))
    if date_from is not None:
        filters.append(GTE(Appointment.start_at, date_from))
    if date_to is not None:
        filters.append(LT(Appointment.start_at, date_to))

    query = Appointment.find(*filters)
    total = await query.count()
    items = await query.sort(+Appointment.start_at, +Appointment.id).skip(skip).limit(page_size).to_list()
    return Page(items=items, total=total, page=page, page_size=page_size)


async def busy_ranges(
    doctor_id: PydanticObjectId, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """(début, fin) des rendez-vous non annulés du médecin qui touchent [start, end)."""
    appointments = await Appointment.find(
        Eq(Appointment.doctor_id, doctor_id),
        LT(Appointment.start_at, end),
        GT(Appointment.end_at, start),
        NE(Appointment.status, AppointmentStatus.CANCELLED),
    ).to_list()
    return [(item.start_at, item.end_at) for item in appointments]


# ── Demandes en langage libre ─────────────────────────────────────────────────


async def insert_request(request: AppointmentRequest) -> AppointmentRequest:
    return await request.insert()


async def get_request(request_id: PydanticObjectId) -> AppointmentRequest | None:
    return await AppointmentRequest.get(request_id)


async def save_request(request: AppointmentRequest) -> AppointmentRequest:
    await request.save()
    return request


# ── Lectures dans les collections d'autres modules (lecture seule) ────────────


async def get_doctor(doctor_id: PydanticObjectId) -> User | None:
    return await User.find_one(
        Eq(User.id, doctor_id), Eq(User.role, Role.DOCTOR), Eq(User.is_active, True)
    )


async def list_doctors(specialty: str | None = None) -> list[User]:
    filters: dict = {"role": Role.DOCTOR.value, "isActive": True}
    if specialty:
        filters["doctorProfile.specialty"] = {"$regex": re.escape(specialty), "$options": "i"}
    return await User.find(filters).sort(+User.last_name, +User.first_name).to_list()


async def get_patient(patient_id: PydanticObjectId) -> Patient | None:
    return await Patient.find_one(Eq(Patient.id, patient_id), Eq(Patient.deleted_at, None))
