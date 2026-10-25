"""Calcul des créneaux libres d'un médecin (fonctions pures, sans base de données)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

from app.modules.appointments.models import DayPart

# La clinique est en Tunisie (UTC+1 toute l'année). Un décalage fixe évite de dépendre
# du paquet `tzdata`, absent par défaut sous Windows.
CLINIC_TZ = timezone(timedelta(hours=1))


@dataclass(frozen=True)
class Slot:
    start_at: datetime
    end_at: datetime


def clinic_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Début (inclus) et fin (exclue) du jour `day` à la clinique, en UTC."""
    start = datetime.combine(day, time.min, tzinfo=CLINIC_TZ)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def day_part_of(local_start: datetime) -> DayPart:
    if local_start.hour < 12:
        return DayPart.MORNING
    if local_start.hour < 17:
        return DayPart.AFTERNOON
    return DayPart.EVENING


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def compute_free_slots(
    availabilities: Iterable,
    day: date,
    day_part: DayPart | None,
    busy: Sequence[tuple[datetime, datetime]],
    now: datetime,
) -> list[Slot]:
    """Créneaux du jour `day` qui sont dans les disponibilités, libres et dans le futur.

    `availabilities` : objets avec `day_of_week` (1 = lundi), `start_time`, `end_time`
    ("HH:MM") et `slot_minutes`. `busy` : (début, fin) des rendez-vous déjà pris.
    """
    slots: list[Slot] = []
    for availability in sorted(availabilities, key=lambda item: item.start_time):
        if availability.day_of_week != day.isoweekday():
            continue
        cursor = datetime.combine(day, _parse_hhmm(availability.start_time), tzinfo=CLINIC_TZ)
        end = datetime.combine(day, _parse_hhmm(availability.end_time), tzinfo=CLINIC_TZ)
        step = timedelta(minutes=availability.slot_minutes)
        while cursor + step <= end:
            slot = Slot(cursor.astimezone(UTC), (cursor + step).astimezone(UTC))
            is_free = not any(b_start < slot.end_at and b_end > slot.start_at for b_start, b_end in busy)
            if (
                is_free
                and slot.start_at > now
                and (day_part is None or day_part_of(cursor) == day_part)
            ):
                slots.append(slot)
            cursor += step
    return slots
