from datetime import UTC, date, datetime, timedelta, timezone

from app.core.time import utc_midnight, utcnow

# Tunisia: UTC+1 all year. "Today" (age, future birth dates) is the clinic's day.
CLINIC_TZ = timezone(timedelta(hours=1))


def clinic_today() -> date:
    return utcnow().astimezone(CLINIC_TZ).date()


def to_mongo_date(day: date) -> datetime:
    """API birth dates are `date`; MongoDB stores them at 00:00 UTC."""
    return utc_midnight(day)


def from_mongo_date(value: datetime) -> date:
    return value.astimezone(UTC).date()


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def age_on(birth_date: date, today: date) -> int:
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)
