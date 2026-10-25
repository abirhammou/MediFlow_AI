"""API schemas of the appointments (camelCase, like the patients module)."""

from datetime import datetime
from typing import Annotated

from app.modules.appointments.models import AppointmentStatus
from app.modules.patients.schemas import Clean, InputModel, OutputModel, _max_length


class AvailabilityOut(OutputModel):
    day_of_week: int  # 1 = Monday
    start_time: str
    end_time: str
    slot_minutes: int


class DoctorOut(OutputModel):
    id: str
    name: str
    specialty: str | None
    office_room: str | None
    availabilities: list[AvailabilityOut]


class SlotOut(OutputModel):
    start_at: datetime
    end_at: datetime


class AppointmentCreate(InputModel):
    """A PATIENT books for their own record (patientId must be absent or their own);
    SECRETARY / ADMIN give the patientId."""

    doctor_id: str
    start_at: datetime
    reason: Annotated[str | None, Clean, _max_length(255)] = None
    patient_id: str | None = None


class AppointmentCancel(InputModel):
    reason: Annotated[str, Clean, _max_length(255)]


class AppointmentOut(OutputModel):
    id: str
    patient_id: str
    patient_name: str | None
    record_number: str | None
    doctor_id: str
    doctor_name: str | None
    specialty: str | None
    start_at: datetime
    end_at: datetime
    reason: str | None
    status: AppointmentStatus
    cancel_reason: str | None
    created_at: datetime


class AppointmentPage(OutputModel):
    items: list[AppointmentOut]
    total: int
    page: int
    size: int
