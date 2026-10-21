# backend/app/core/campus_rules.py
"""Constants and PURE rules for campus scheduling (no DB, no clock reads).

Eligibility is decided only by overlapping DEPARTURE WINDOWS. Row creation time
is never consulted. Datetimes handed to these functions may be aware (any
offset) or naive; naive values are interpreted as stored naive-UTC (the DB
convention) so ORM rows can be passed in directly. ``validate_window`` is the
exception: it validates API input and rejects naive values.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Tuple

from app.core import campus_time

RULE_VERSION = "window-overlap-v1"
MAX_WINDOW_HOURS = 6
MAX_LEAD_DAYS = 14
MIN_WINDOW_MINUTES = 10
FLEX_MINUTES = 30
MAX_OPEN_REQUESTS_PER_USER = 3
PROPOSAL_TTL_MINUTES = 30
SUGGESTION_TTL_MINUTES = 15
RECENT_ENDED_HOURS = 24
ESTIMATE_TTL_MINUTES = 360
ESTIMATE_RETRY_SECONDS = 60
OUTBOX_MAX_ATTEMPTS = 8
OUTBOX_BACKOFF_BASE_SECONDS = 5
OUTBOX_BACKOFF_MAX_SECONDS = 300
TRANSPORT_RESPONSIBILITY_TEXT = (
    "Participants arrange and pay for the taxi themselves. "
    "This agreement is not a booking, dispatch or safety guarantee."
)
REQUEST_EXPIRY_GRACE_HOURS = 1  # expires_at may be at most latest_departure + this

# Stable reason codes
REASON_WINDOW_OVERLAP = "WINDOW_OVERLAP"
REASON_FLEXIBLE_WINDOW = "FLEXIBLE_WINDOW"
REASON_DIFFERENT_USER = "different_user"
REASON_DIFFERENT_COLLEGE = "different_college"
REASON_DIFFERENT_CORRIDOR = "different_corridor"
REASON_OPPOSITE_DIRECTION = "opposite_direction"
REASON_NOT_OPEN = "not_open"
REASON_EXPIRED = "expired"
REASON_DISJOINT = "disjoint_windows"

# Stable validate_window error messages
ERR_NAIVE = "naive_datetime"
ERR_ORDER = "latest_must_be_after_earliest"
ERR_TOO_SHORT = "window_too_short"
ERR_TOO_LONG = "window_too_long"
ERR_ALREADY_ENDED = "window_already_ended"
ERR_TOO_FAR = "window_too_far_ahead"

WARNING_CANNOT_MEET_ARRIVE_BY = "cannot_meet_arrive_by"
WARNING_DEADLINE_UNVERIFIED = "deadline_unverified"


def _utc(dt: datetime) -> datetime:
    return campus_time.from_db(dt)


def validate_window(earliest: datetime, latest: datetime, now: datetime) -> None:
    """Validate a requested departure window; raise ValueError(<stable code>)."""
    for value in (earliest, latest, now):
        if value is None or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(ERR_NAIVE)
    if latest <= earliest:
        raise ValueError(ERR_ORDER)
    length = latest - earliest
    if length < timedelta(minutes=MIN_WINDOW_MINUTES):
        raise ValueError(ERR_TOO_SHORT)
    if length > timedelta(hours=MAX_WINDOW_HOURS):
        raise ValueError(ERR_TOO_LONG)
    if latest <= now:
        raise ValueError(ERR_ALREADY_ENDED)
    if earliest > now + timedelta(days=MAX_LEAD_DAYS):
        raise ValueError(ERR_TOO_FAR)


def windows_overlap(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> Optional[Tuple[datetime, datetime]]:
    """Inclusive intersection of two windows, or None. Touching windows overlap
    on a single instant: [0,3] and [3,5] -> (3,3)."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start <= end:
        return start, end
    return None


@dataclass(frozen=True)
class Eligibility:
    ok: bool
    reason: str
    feasible_start: Optional[datetime] = None
    feasible_end: Optional[datetime] = None


def _val(x: Any) -> Any:
    """Enum -> its value so enum members and plain strings compare equal."""
    return getattr(x, "value", x)


def _not_ok(reason: str) -> Eligibility:
    return Eligibility(False, reason, None, None)


def eligible_pair(req_a: Any, req_b: Any, now: datetime) -> Eligibility:
    """Can these two travel requests be suggested to each other at ``now``?

    Check order (first failure wins): different_user, different_college,
    opposite_direction / different_corridor, not_open, expired,
    disjoint_windows. Creation time is never read.
    """
    now = _utc(now)
    if req_a.user_id == req_b.user_id:
        return _not_ok(REASON_DIFFERENT_USER)
    if req_a.college_id != req_b.college_id:
        return _not_ok(REASON_DIFFERENT_COLLEGE)
    same_leg = (
        _val(req_a.mode) == _val(req_b.mode)
        and req_a.origin_landmark_id == req_b.origin_landmark_id
        and req_a.hub_id == req_b.hub_id
    )
    if not same_leg:
        return _not_ok(REASON_DIFFERENT_CORRIDOR)
    if _val(req_a.direction) != _val(req_b.direction):
        return _not_ok(REASON_OPPOSITE_DIRECTION)
    if _val(req_a.status) != "OPEN" or _val(req_b.status) != "OPEN":
        return _not_ok(REASON_NOT_OPEN)
    for r in (req_a, req_b):
        if _utc(r.expires_at) <= now or _utc(r.latest_departure) <= now:
            return _not_ok(REASON_EXPIRED)

    a_start, a_end = _utc(req_a.earliest_departure), _utc(req_a.latest_departure)
    b_start, b_end = _utc(req_b.earliest_departure), _utc(req_b.latest_departure)

    hit = windows_overlap(a_start, a_end, b_start, b_end)
    if hit:
        return Eligibility(True, REASON_WINDOW_OVERLAP, hit[0], hit[1])

    if req_a.flexibility_consent and req_b.flexibility_consent:
        flex = timedelta(minutes=FLEX_MINUTES)
        hit = windows_overlap(a_start - flex, a_end + flex, b_start - flex, b_end + flex)
        if hit:
            return Eligibility(True, REASON_FLEXIBLE_WINDOW, hit[0], hit[1])
    return _not_ok(REASON_DISJOINT)


def deadline_warnings(
    req_a: Any, req_b: Any, earliest_feasible_departure: datetime, estimate: Any
) -> List[str]:
    """Warning codes about ``arrive_by`` deadlines.

    A party departs at the EARLIEST feasible instant (callers pass
    ``max(feasible_start, now)``), not at the end of the window, so the test is
    ``earliest_feasible_departure + duration > earliest arrive_by``.
    ``estimate`` is an object or mapping with ``status`` ("VERIFIED"/"UNVERIFIED")
    and ``duration_s``; None is treated as UNVERIFIED. No arrive_by -> no warnings.
    """
    deadlines = [_utc(r.arrive_by) for r in (req_a, req_b) if r.arrive_by is not None]
    if not deadlines:
        return []
    if isinstance(estimate, Mapping):
        status, duration = estimate.get("status"), estimate.get("duration_s")
    else:
        status = getattr(estimate, "status", None)
        duration = getattr(estimate, "duration_s", None)
    if _val(status) == "VERIFIED" and duration is not None:
        arrival = _utc(earliest_feasible_departure) + timedelta(seconds=duration)
        if any(arrival > d for d in deadlines):
            return [WARNING_CANNOT_MEET_ARRIVE_BY]
        return []
    return [WARNING_DEADLINE_UNVERIFIED]


# ---- small pure helpers shared by the route modules -------------------------

def pair_key(id_a: int, id_b: int) -> Tuple[int, int]:
    """(low, high) ordering used by PairSuggestion and the pending-proposal index."""
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def agreed_departure(
    feasible_start: datetime, feasible_end: datetime, now: datetime
) -> Optional[datetime]:
    """max(feasible_start, now rounded UP to the minute); None if past feasible_end."""
    candidate = max(_utc(feasible_start), campus_time.ceil_minute(_utc(now)))
    return candidate if candidate <= _utc(feasible_end) else None


def proposal_expires_at(now: datetime, req_a: Any, req_b: Any) -> datetime:
    """now + PROPOSAL_TTL_MINUTES, never later than the earlier latest_departure."""
    cap = min(_utc(req_a.latest_departure), _utc(req_b.latest_departure))
    return min(_utc(now) + timedelta(minutes=PROPOSAL_TTL_MINUTES), cap)


def resolve_request_expiry(latest_departure: datetime, requested: Optional[datetime]) -> datetime:
    """Default expires_at = latest_departure; never later than latest + 1h."""
    latest = _utc(latest_departure)
    if requested is None:
        return latest
    return min(_utc(requested), latest + timedelta(hours=REQUEST_EXPIRY_GRACE_HOURS))


def backoff_seconds(attempts: int) -> int:
    """Outbox retry delay after ``attempts`` failed attempts (capped)."""
    return min(OUTBOX_BACKOFF_BASE_SECONDS * (2 ** attempts), OUTBOX_BACKOFF_MAX_SECONDS)
