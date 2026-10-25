from datetime import UTC, date, datetime, timedelta

from beanie import PydanticObjectId
from fastapi import HTTPException

from app.core.pagination import Page
from app.core.time import utcnow
from app.dependencies import owns_patient_record
from app.errors import APIError, LLMResponseError, LLMTimeoutError
from app.llm.service import generate_json
from app.modules.appointments import repository
from app.modules.appointments.models import (
    Appointment,
    AppointmentRequest,
    AppointmentStatus,
    ParsedRequest,
)
from app.modules.appointments.prompts import SYSTEM_PROMPT, intent_prompt
from app.modules.appointments.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentIntent,
    AppointmentOut,
    AppointmentUpdate,
    ParseRequestIn,
    ParseRequestOut,
    SlotOut,
)
from app.modules.appointments.slots import CLINIC_TZ, clinic_day_bounds, compute_free_slots
from app.modules.auth.models import Role, User

LLM_ATTEMPTS = 3

DEFAULT_DURATION = timedelta(minutes=30)
MAX_PROPOSED_SLOTS = 20


def _serialize(appointment: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=str(appointment.id),
        patient_id=str(appointment.patient_id),
        doctor_id=str(appointment.doctor_id),
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        reason=appointment.reason,
        status=appointment.status,
        cancel_reason=appointment.cancel_reason,
    )


class AppointmentService:
    """Logique métier des rendez-vous. `repo` est remplaçable dans les tests."""

    def __init__(self, repo=repository) -> None:
        self.repo = repo

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(self, data: AppointmentCreate, user: User) -> AppointmentOut:
        if user.role == Role.PATIENT:
            owns_patient_record(user, str(data.patient_id))
        if await self.repo.get_patient(data.patient_id) is None:
            raise APIError(404, "patient_not_found", "Patient introuvable.")
        if await self.repo.get_doctor(data.doctor_id) is None:
            raise APIError(404, "doctor_not_found", "Médecin introuvable.")

        end_at = data.end_at or data.start_at + DEFAULT_DURATION
        if end_at <= data.start_at:
            raise APIError(422, "invalid_time_range", "La fin doit être après le début.")
        if data.start_at <= utcnow():
            raise APIError(422, "appointment_in_past", "Le rendez-vous doit être dans le futur.")
        await self._ensure_slot_is_free(data.doctor_id, data.start_at, end_at)

        appointment = await self.repo.insert_appointment(
            Appointment(
                patient_id=data.patient_id,
                doctor_id=data.doctor_id,
                start_at=data.start_at,
                end_at=end_at,
                reason=data.reason,
                # Une demande de patient doit être confirmée par le secrétariat.
                status=(
                    AppointmentStatus.PENDING
                    if user.role == Role.PATIENT
                    else AppointmentStatus.CONFIRMED
                ),
                created_by=user.id,
            )
        )
        if data.request_id is not None:
            request = await self.repo.get_request(data.request_id)
            if request is not None:
                request.appointment_id = appointment.id
                await self.repo.save_request(request)
        return _serialize(appointment)

    async def list_appointments(
        self,
        user: User,
        *,
        patient_id: PydanticObjectId | None = None,
        doctor_id: PydanticObjectId | None = None,
        status: AppointmentStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[AppointmentOut]:
        # Un patient ne voit que les siens, un médecin que les siens.
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                return Page(items=[], total=0, page=page, page_size=page_size)
            patient_id = user.patient_id
        elif user.role == Role.DOCTOR:
            doctor_id = user.id
        result = await self.repo.list_appointments(
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        return Page(
            items=[_serialize(item) for item in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    async def get(self, appointment_id: PydanticObjectId, user: User) -> AppointmentOut:
        return _serialize(await self._get_accessible(appointment_id, user))

    async def update(
        self, appointment_id: PydanticObjectId, changes: AppointmentUpdate, user: User
    ) -> AppointmentOut:
        if changes.status == AppointmentStatus.CANCELLED:
            raise APIError(422, "use_cancel_route", "Pour annuler, utiliser POST /{id}/cancel.")
        appointment = await self._get_accessible(appointment_id, user)
        if appointment.status == AppointmentStatus.CANCELLED:
            raise APIError(409, "appointment_cancelled", "Ce rendez-vous est annulé.")

        doctor_id = changes.doctor_id or appointment.doctor_id
        start_at = changes.start_at or appointment.start_at
        if changes.end_at is not None:
            end_at = changes.end_at
        else:  # on garde la durée si seul le début change
            end_at = start_at + (appointment.end_at - appointment.start_at)
        if end_at <= start_at:
            raise APIError(422, "invalid_time_range", "La fin doit être après le début.")

        moved = (doctor_id, start_at, end_at) != (
            appointment.doctor_id,
            appointment.start_at,
            appointment.end_at,
        )
        if moved:
            if changes.doctor_id and await self.repo.get_doctor(changes.doctor_id) is None:
                raise APIError(404, "doctor_not_found", "Médecin introuvable.")
            await self._ensure_slot_is_free(doctor_id, start_at, end_at, exclude_id=appointment.id)

        appointment.doctor_id = doctor_id
        appointment.start_at = start_at
        appointment.end_at = end_at
        if changes.reason is not None:
            appointment.reason = changes.reason
        if changes.status is not None:
            appointment.status = changes.status
        return _serialize(await self.repo.save_appointment(appointment))

    async def cancel(
        self, appointment_id: PydanticObjectId, body: AppointmentCancel, user: User
    ) -> AppointmentOut:
        appointment = await self._get_accessible(appointment_id, user)
        if appointment.status == AppointmentStatus.CANCELLED:
            raise APIError(409, "appointment_cancelled", "Ce rendez-vous est déjà annulé.")
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancel_reason = body.cancel_reason
        return _serialize(await self.repo.save_appointment(appointment))

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def _extract_intent(self, message: str, today: date) -> AppointmentIntent:
        """Appelle le LLM ; les fournisseurs gratuits échouent parfois ponctuellement, on réessaie."""
        last_error: APIError | None = None
        for _ in range(LLM_ATTEMPTS):
            try:
                return await generate_json(
                    module="appointments",
                    system=SYSTEM_PROMPT,
                    user=intent_prompt(message, today),
                    output_schema=AppointmentIntent,
                )
            except (LLMResponseError, LLMTimeoutError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def parse_request(self, body: ParseRequestIn, user: User) -> ParseRequestOut:
        """Transforme un message libre en demande structurée, puis cherche des créneaux réels.

        Garde-fou : le LLM ne reçoit que le texte du message et la date du jour. Les
        disponibilités viennent uniquement de la base de données.
        """
        patient_id = body.patient_id
        if user.role == Role.PATIENT:
            patient_id = user.patient_id

        now = utcnow()
        today = now.astimezone(CLINIC_TZ).date()
        intent = await self._extract_intent(body.message, today)

        request = await self.repo.insert_request(
            AppointmentRequest(
                raw_message=body.message,
                parsed=ParsedRequest(
                    preferred_date=(
                        datetime.combine(intent.preferred_date, datetime.min.time(), tzinfo=UTC)
                        if intent.preferred_date
                        else None
                    ),
                    day_part=intent.day_part,
                    doctor_id=body.doctor_id,
                    specialty=intent.specialty,
                    reason=intent.reason,
                ),
                patient_id=patient_id,
                created_by=user.id,
            )
        )
        slots = await self._find_slots(intent, body.doctor_id, now)
        return ParseRequestOut(request_id=str(request.id), parsed=intent, available_slots=slots)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _find_slots(
        self, intent: AppointmentIntent, doctor_id: PydanticObjectId | None, now: datetime
    ) -> list[SlotOut]:
        if intent.preferred_date is None:
            return []
        if doctor_id is not None:
            doctor = await self.repo.get_doctor(doctor_id)
            doctors = [doctor] if doctor is not None else []
        else:
            doctors = await self.repo.list_doctors(intent.specialty)

        day_start, day_end = clinic_day_bounds(intent.preferred_date)
        proposed: list[SlotOut] = []
        for doctor in doctors:
            if doctor.doctor_profile is None:
                continue
            busy = await self.repo.busy_ranges(doctor.id, day_start, day_end)
            for slot in compute_free_slots(
                doctor.doctor_profile.availabilities, intent.preferred_date, intent.day_part, busy, now
            ):
                proposed.append(
                    SlotOut(
                        doctor_id=str(doctor.id),
                        doctor_name=f"{doctor.first_name} {doctor.last_name}",
                        start_at=slot.start_at,
                        end_at=slot.end_at,
                    )
                )
        proposed.sort(key=lambda item: (item.start_at, item.doctor_name))
        return proposed[:MAX_PROPOSED_SLOTS]

    async def _ensure_slot_is_free(
        self,
        doctor_id: PydanticObjectId,
        start_at: datetime,
        end_at: datetime,
        exclude_id: PydanticObjectId | None = None,
    ) -> None:
        clash = await self.repo.find_overlapping_appointment(
            doctor_id, start_at, end_at, exclude_id=exclude_id
        )
        if clash is not None:
            raise APIError(409, "slot_taken", "Ce créneau est déjà réservé pour ce médecin.")

    async def _get_accessible(self, appointment_id: PydanticObjectId, user: User) -> Appointment:
        appointment = await self.repo.get_appointment(appointment_id)
        if appointment is None:
            raise APIError(404, "appointment_not_found", "Rendez-vous introuvable.")
        if user.role == Role.PATIENT:
            owns_patient_record(user, str(appointment.patient_id))
        elif user.role == Role.DOCTOR and appointment.doctor_id != user.id:
            raise HTTPException(status_code=403, detail="Ce rendez-vous n'est pas le vôtre.")
        return appointment
