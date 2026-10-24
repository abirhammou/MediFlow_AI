from datetime import UTC, date, datetime, time


def utcnow() -> datetime:
    """Current UTC time, truncated to milliseconds (BSON dates have millisecond precision)."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def utc_midnight(day: date) -> datetime:
    """BSON has no date-only type: date-only values are stored at 00:00 UTC."""
    return datetime.combine(day, time.min, tzinfo=UTC)
