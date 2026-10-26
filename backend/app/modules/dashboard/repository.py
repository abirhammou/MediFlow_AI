from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GTE, GT, LT, NE, Eq

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
    """Compte les tâches FollowUp via Motor (collection non-Beanie)."""
    try:
        # Récupère le moteur Motor via le client Beanie
        import beanie
        motor_client = beanie.Document.get_settings()  # type: ignore
    except Exception:
        pass
    try:
        # Accès via pymongo asynchrone : le client Beanie est le même que Motor
        from pymongo import AsyncMongoClient
        from app.core.config import settings
        client = AsyncMongoClient(settings.mongodb_uri)
        col = client[settings.mongodb_db]["followup_tasks"]
        pending   = await col.count_documents({"status": "pending"})
        done      = await col.count_documents({"status": "done"})
        cancelled = await col.count_documents({"status": "cancelled"})
        return {"pending": pending, "done": done, "cancelled": cancelled}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("count_followup_tasks failed: %s", exc)
        return {"pending": 0, "done": 0, "cancelled": 0}


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
