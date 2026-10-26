"""/api/booking: doctors, free slots, booking, confirmation and cancellation (patient portal)."""

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_roles
from app.modules.appointment_booking.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentOut,
    AppointmentPage,
    DoctorOut,
    SlotOut,
)
from app.modules.appointment_booking.service import APPOINTMENT_ROLES, AppointmentService
from app.modules.appointments.models import AppointmentStatus
from app.modules.auth.models import User

router = APIRouter()
PREFIX = "/api/booking"
TAGS = ["appointment_booking"]
# The free-text request parsing (Appointment Manager AI) lives in /api/appointments.
LLM_ENABLED = False

readers = require_roles(*APPOINTMENT_ROLES["read"])
bookers = require_roles(*APPOINTMENT_ROLES["book"])
managers = require_roles(*APPOINTMENT_ROLES["manage"])


def get_appointment_service() -> AppointmentService:
    return AppointmentService()


@router.get("/doctors", response_model=list[DoctorOut])
async def list_doctors(
    _: User = Depends(readers),
    service: AppointmentService = Depends(get_appointment_service),
) -> list[DoctorOut]:
    """Active doctors with their weekly availabilities."""
    return await service.doctors()


@router.get("/slots", response_model=list[SlotOut])
async def free_slots(
    doctor_id: str = Query(alias="doctorId"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    _: User = Depends(readers),
    service: AppointmentService = Depends(get_appointment_service),
) -> list[SlotOut]:
    """Free slots of a doctor (clinic days, inclusive; default: the next 14 days)."""
    return await service.slots(doctor_id, date_from, date_to)


@router.get("", response_model=AppointmentPage)
async def list_appointments(
    status_filter: AppointmentStatus | None = Query(default=None, alias="status"),
    upcoming: bool = False,
    patient_id: str | None = Query(default=None, alias="patientId"),
    doctor_id: str | None = Query(default=None, alias="doctorId"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(readers),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentPage:
    """PATIENT: their own; DOCTOR: theirs; staff: everything, with filters."""
    return await service.search(
        user,
        status=status_filter,
        upcoming=upcoming,
        patient_id=patient_id,
        doctor_id=doctor_id,
        page=page,
        size=size,
    )


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    data: AppointmentCreate,
    user: User = Depends(bookers),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentOut:
    """PATIENT: a PENDING request for their own record; staff: a CONFIRMED appointment."""
    return await service.book(user, data)


@router.post("/{appointment_id}/confirm", response_model=AppointmentOut)
async def confirm_appointment(
    appointment_id: str,
    user: User = Depends(managers),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentOut:
    return await service.confirm(user, appointment_id)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: str,
    data: AppointmentCancel,
    user: User = Depends(bookers),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentOut:
    """A PATIENT cancels their own upcoming appointments; staff any active one."""
    return await service.cancel(user, appointment_id, data)
