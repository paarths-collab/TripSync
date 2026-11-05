# backend/app/core/campus_time.py
"""Time helpers for campus scheduling.

Storage convention: every campus datetime column is a NAIVE UTC ``DateTime`` so
SQLite (tests) and PostgreSQL behave identically. Everything above the DB layer
works with timezone-aware datetimes. Convert at the boundary with ``to_db`` /
``from_db``.

ALWAYS call ``campus_time.utcnow()`` through the module (never
``from campus_time import utcnow``) so tests can monkeypatch the clock.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(UTC)


def _require_aware(dt: datetime, what: str = "datetime") -> None:
    if not isinstance(dt, datetime):
        raise ValueError(f"{what} must be a datetime")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"naive {what} is not allowed; supply a timezone offset")


def to_db(dt: datetime) -> datetime:
    """Aware datetime -> naive UTC for storage. Naive input raises ValueError."""
    _require_aware(dt)
    return dt.astimezone(UTC).replace(tzinfo=None)


def from_db(dt: datetime) -> datetime:
    """Naive UTC (as stored) -> aware UTC. Already-aware input is normalised to UTC."""
    if not isinstance(dt, datetime):
        raise ValueError("value must be a datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_tz(name: str) -> ZoneInfo:
    """Validated IANA zone (e.g. "Asia/Kolkata"); anything else raises ValueError."""
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError(f"invalid timezone: {name!r}")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError, KeyError) as exc:
        raise ValueError(f"invalid timezone: {name!r}") from exc


def local_iso(dt: datetime, tz_name: str) -> str:
    """ISO-8601 string for ``dt`` rendered in ``tz_name`` with its UTC offset."""
    _require_aware(dt)
    return dt.astimezone(parse_tz(tz_name)).isoformat()


def utc_iso(dt: datetime) -> str:
    """ISO-8601 UTC string ending in ``Z``. Naive input is treated as stored UTC."""
    return from_db(dt).isoformat().replace("+00:00", "Z")


def ceil_minute(dt: datetime) -> datetime:
    """Round up to the next whole minute (unchanged when already on a minute)."""
    _require_aware(dt)
    floor = dt.replace(second=0, microsecond=0)
    return floor if floor == dt else floor + timedelta(minutes=1)
