"""Appointments: free slots from the doctors' weekly availabilities, booking, confirmation.

A PATIENT books a PENDING appointment for their own record (never another one) that the
secretary confirms; staff bookings are CONFIRMED at once. No double booking: the slot
must be free in the doctor's grid, `find_overlapping_appointment` refuses any overlap,
and the unique index uq_appt_doctor_slot settles two bookings at the same instant.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import GTE, LT, Eq, In
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.time import utcnow
from app.errors import APIError
from app.modules.appointment_booking.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentOut,
    AppointmentPage,
    AvailabilityOut,
    DoctorOut,
    SlotOut,
)
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.appointments.repository import find_overlapping_appointment
from app.modules.auth.models import Role, User
from app.modules.patients import repository as patients
from app.modules.patients.dates import CLINIC_TZ, clinic_today
from app.modules.patients.models import Patient

# Who may do what (the frontend mirrors it).
APPOINTMENT_ROLES: dict[str, tuple[Role, ...]] = {
    "read": (Role.PATIENT, Role.DOCTOR, Role.SECRETARY, Role.ADMIN),
    "book": (Role.PATIENT, Role.SECRETARY, Role.ADMIN),
    "manage": (Role.SECRETARY, Role.ADMIN),  # confirm, any patient
}
ACTIVE = [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
BOOKING_HORIZON_DAYS = 60
MAX_SLOT_RANGE_DAYS = 31
MIN_NOTICE = timedelta(hours=1)
MAX_PENDING_PER_PATIENT = 3


def _oid(value: str | None, code: str, detail: str, status: int = 404) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError):
        raise APIError(status, code, detail) from None


def _not_found() -> APIError:
    return APIError(404, "appointment_not_found", "Rendez-vous introuvable.")


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def doctor_slots(doctor: User, first: date, last: date) -> list[tuple[datetime, datetime]]:
    """Every slot of the doctor's weekly grid between two clinic days (inclusive)."""
    profile = doctor.doctor_profile
    if profile is None:
        return []
    slots = []
    day = first
    while day <= last:
        for availability in profile.availabilities:
            if availability.day_of_week != day.isoweekday():
                continue
            start = _minutes(availability.start_time)
            end = _minutes(availability.end_time)
            for minute in range(
                start, end - availability.slot_minutes + 1, availability.slot_minutes
            ):
                start_at = datetime.combine(day, time(minute // 60, minute % 60), CLINIC_TZ)
                slots.append((start_at, start_at + timedelta(minutes=availability.slot_minutes)))
        day += timedelta(days=1)
    return sorted(slots)


async def _doctor(doctor_id: str) -> User:
    oid = _oid(doctor_id, "doctor_not_found", "Médecin introuvable.")
    doctor = await User.get(oid)
    if doctor is None or doctor.role != Role.DOCTOR or not doctor.is_active:
        raise APIError(404, "doctor_not_found", "Médecin introuvable.")
    return doctor


async def _free_slots(doctor: User, first: date, last: date) -> list[tuple[datetime, datetime]]:
    grid = doctor_slots(doctor, first, last)
    if not grid:
        return []
    taken = await Appointment.find(
        Eq(Appointment.doctor_id, doctor.id),
        In(Appointment.status, ACTIVE),
        LT(Appointment.start_at, grid[-1][1]),
        GTE(Appointment.end_at, grid[0][0]),
    ).to_list()
    earliest = utcnow() + MIN_NOTICE
    return [
        (start, end)
        for start, end in grid
        if start >= earliest and not any(a.start_at < end and a.end_at > start for a in taken)
    ]


class AppointmentService:
    async def doctors(self) -> list[DoctorOut]:
        doctors = await User.find(Eq(User.role, Role.DOCTOR), Eq(User.is_active, True)).to_list()
        return [
            DoctorOut(
                id=str(d.id),
                name=f"{d.first_name} {d.last_name}",
                specialty=d.doctor_profile.specialty if d.doctor_profile else None,
                office_room=d.doctor_profile.office_room if d.doctor_profile else None,
                availabilities=[
                    AvailabilityOut(**a.model_dump())
                    for a in (d.doctor_profile.availabilities if d.doctor_profile else [])
                ],
            )
            for d in sorted(doctors, key=lambda d: (d.last_name, d.first_name))
        ]

    async def slots(self, doctor_id: str, first: date | None, last: date | None) -> list[SlotOut]:
        doctor = await _doctor(doctor_id)
        today = clinic_today()
        first = max(first or today, today)
        last = min(last or first + timedelta(days=13), today + timedelta(days=BOOKING_HORIZON_DAYS))
        if last < first:
            return []
        if (last - first).days >= MAX_SLOT_RANGE_DAYS:
            raise APIError(422, "invalid_period", f"Période limitée à {MAX_SLOT_RANGE_DAYS} jours.")
        return [SlotOut(start_at=s, end_at=e) for s, e in await _free_slots(doctor, first, last)]

    async def _out(
        self, appointments: list[Appointment], *, with_patient: bool
    ) -> list[AppointmentOut]:
        doctor_ids = {a.doctor_id for a in appointments}
        doctors = {d.id: d for d in await User.find(In(User.id, list(doctor_ids))).to_list()}
        people: dict[PydanticObjectId, Patient] = {}
        if with_patient:
            found = await Patient.find(
                In(Patient.id, list({a.patient_id for a in appointments}))
            ).to_list()
            people = {p.id: p for p in found if p.id}
        result = []
        for a in appointments:
            doctor = doctors.get(a.doctor_id)
            patient = people.get(a.patient_id)
            result.append(
                AppointmentOut(
                    id=str(a.id),
                    patient_id=str(a.patient_id),
                    patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
                    record_number=patient.record_number if patient else None,
                    doctor_id=str(a.doctor_id),
                    doctor_name=f"{doctor.first_name} {doctor.last_name}" if doctor else None,
                    specialty=doctor.doctor_profile.specialty
                    if doctor and doctor.doctor_profile
                    else None,
                    start_at=a.start_at,
                    end_at=a.end_at,
                    reason=a.reason,
                    status=a.status,
                    cancel_reason=a.cancel_reason,
                    created_at=a.created_at,
                )
            )
        return result

    async def search(
        self,
        user: User,
        *,
        status: AppointmentStatus | None,
        upcoming: bool,
        patient_id: str | None,
        doctor_id: str | None,
        page: int,
        size: int,
    ) -> AppointmentPage:
        query: dict[str, Any] = {}
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                return AppointmentPage(items=[], total=0, page=page, size=size)
            query["patientId"] = user.patient_id  # never chosen by the patient
        elif user.role == Role.DOCTOR:
            query["doctorId"] = user.id
        else:
            if patient_id:
                query["patientId"] = _oid(
                    patient_id, "invalid_patient_id", "Identifiant patient invalide.", 422
                )
            if doctor_id:
                query["doctorId"] = _oid(
                    doctor_id, "invalid_doctor_id", "Identifiant médecin invalide.", 422
                )
        if status is not None:
            query["status"] = status.value
        if upcoming:
            query["endAt"] = {"$gte": utcnow()}
        finder = Appointment.find(query)
        total = await finder.count()
        order = 1 if upcoming else -1
        items = (
            await finder.sort([("startAt", order)]).skip((page - 1) * size).limit(size).to_list()
        )
        return AppointmentPage(
            items=await self._out(items, with_patient=user.role != Role.PATIENT),
            total=total,
            page=page,
            size=size,
        )

    async def book(self, user: User, data: AppointmentCreate) -> AppointmentOut:
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                raise APIError(
                    403, "no_patient_record", "Votre compte n'est relié à aucun dossier patient."
                )
            if data.patient_id is not None and data.patient_id != str(user.patient_id):
                raise APIError(
                    403, "not_your_record", "Vous ne pouvez réserver que pour votre propre dossier."
                )
            patient_id = user.patient_id
            pending = await Appointment.find(
                Eq(Appointment.patient_id, patient_id),
                Eq(Appointment.status, AppointmentStatus.PENDING),
                GTE(Appointment.start_at, utcnow()),
            ).count()
            if pending >= MAX_PENDING_PER_PATIENT:
                raise APIError(
                    409,
                    "too_many_requests",
                    f"Vous avez déjà {pending} demandes en attente de confirmation.",
                )
            status = AppointmentStatus.PENDING
        else:
            if not data.patient_id:
                raise APIError(422, "patient_required", "Indiquez le patient.")
            patient_id = _oid(data.patient_id, "patient_not_found", "Dossier patient introuvable.")
            status = AppointmentStatus.CONFIRMED
        if await patients.get_patient(patient_id) is None:
            raise APIError(404, "patient_not_found", "Dossier patient introuvable.")

        doctor = await _doctor(data.doctor_id)
        start = data.start_at.astimezone(CLINIC_TZ)
        free = dict(await _free_slots(doctor, start.date(), start.date()))
        end = free.get(start)
        if end is None:
            raise APIError(
                409, "slot_unavailable", "Ce créneau n'est pas disponible. Choisissez-en un autre."
            )
        assert doctor.id is not None
        if await find_overlapping_appointment(doctor.id, start, end) is not None:
            raise APIError(409, "slot_unavailable", "Ce créneau vient d'être réservé.")
        try:
            appointment = await Appointment(
                patient_id=patient_id,
                doctor_id=doctor.id,
                start_at=start,
                end_at=end,
                reason=data.reason,
                status=status,
                created_by=user.id,
            ).insert()
        except DuplicateKeyError:
            raise APIError(409, "slot_unavailable", "Ce créneau vient d'être réservé.") from None
        return (await self._out([appointment], with_patient=user.role != Role.PATIENT))[0]

    async def _appointment(self, user: User, appointment_id: str) -> Appointment:
        appointment = await Appointment.get(
            _oid(appointment_id, "appointment_not_found", "Rendez-vous introuvable.")
        )
        if appointment is None:
            raise _not_found()
        if user.role == Role.PATIENT and appointment.patient_id != user.patient_id:
            raise _not_found()  # another patient's appointment: same answer as missing
        if user.role == Role.DOCTOR and appointment.doctor_id != user.id:
            raise _not_found()
        return appointment

    async def _transition(
        self, appointment: Appointment, allowed: list[AppointmentStatus], changes: dict[str, Any]
    ) -> Appointment:
        document = await Appointment.get_pymongo_collection().find_one_and_update(
            {"_id": appointment.id, "status": {"$in": [s.value for s in allowed]}},
            {"$set": {**changes, "updatedAt": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise APIError(409, "appointment_locked", "Ce rendez-vous a déjà été traité.")
        return Appointment.model_validate(document)

    async def confirm(self, user: User, appointment_id: str) -> AppointmentOut:
        appointment = await self._appointment(user, appointment_id)
        updated = await self._transition(
            appointment, [AppointmentStatus.PENDING], {"status": AppointmentStatus.CONFIRMED.value}
        )
        return (await self._out([updated], with_patient=True))[0]

    async def cancel(
        self, user: User, appointment_id: str, data: AppointmentCancel
    ) -> AppointmentOut:
        appointment = await self._appointment(user, appointment_id)
        if user.role == Role.DOCTOR:
            raise APIError(403, "forbidden", "L'annulation passe par le secrétariat.")
        if user.role == Role.PATIENT and appointment.start_at <= utcnow():
            raise APIError(
                409, "appointment_past", "Un rendez-vous passé ne peut plus être annulé."
            )
        updated = await self._transition(
            appointment,
            ACTIVE,
            {"status": AppointmentStatus.CANCELLED.value, "cancelReason": data.reason},
        )
        return (await self._out([updated], with_patient=user.role != Role.PATIENT))[0]
