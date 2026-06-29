from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc


def utc_now() -> datetime:
    """
    Return the current UTC datetime as a timezone-aware datetime.
    """
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """
    Return the current UTC datetime as an ISO-8601 string.
    """
    return utc_now().isoformat()


def ensure_utc(value: datetime) -> datetime:
    """
    Convert a datetime to timezone-aware UTC.

    Naive datetimes are assumed to already represent UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def parse_datetime(value: str | datetime | date) -> datetime:
    """
    Parse a string, date, or datetime into a timezone-aware UTC datetime.

    Supports common ISO strings, including strings ending with 'Z'.
    """
    if isinstance(value, datetime):
        return ensure_utc(value)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)

    cleaned = value.strip()

    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    parsed = datetime.fromisoformat(cleaned)
    return ensure_utc(parsed)


def parse_date(value: str | datetime | date) -> date:
    """
    Parse a string, date, or datetime into a date.
    """
    if isinstance(value, datetime):
        return ensure_utc(value).date()

    if isinstance(value, date):
        return value

    return parse_datetime(value).date()


def to_iso_datetime(value: str | datetime | date) -> str:
    """
    Convert a string, date, or datetime into a UTC ISO-8601 datetime string.
    """
    return parse_datetime(value).isoformat()


def to_iso_date(value: str | datetime | date) -> str:
    """
    Convert a string, date, or datetime into an ISO date string.
    """
    return parse_date(value).isoformat()


def market_date(value: str | datetime | date) -> date:
    """
    Normalize a timestamp-like value to a market date.

    This currently returns the UTC date. Later, this can be expanded to use
    exchange-specific calendars.
    """
    return parse_date(value)


def convert_timezone(value: str | datetime | date, tz_name: str) -> datetime:
    """
    Convert a timestamp-like value from UTC into another timezone.

    Example:
        convert_timezone("2026-05-22T14:30:00Z", "America/New_York")
    """
    parsed = parse_datetime(value)
    return parsed.astimezone(ZoneInfo(tz_name))
