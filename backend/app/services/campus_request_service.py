# backend/app/services/campus_request_service.py
"""Travel-request lifecycle for campus scheduling (create / read / edit / cancel).

Conventions (see app.core.campus_rules / campus_time):
- datetimes in the DB are naive UTC; API-facing code uses aware datetimes;
- owner-only access answers 404 (never 403) so request ids cannot be enumerated;
- the request row is locked (SELECT ... FOR UPDATE) before any decision is made
  and before proposals/suggestions are touched; helpers here never commit
  unless their docstring says so, the route layer commits.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import campus_rules, campus_time
from app.models.campus_model import (
    CampusLandmark,
    ConnectionProposal,
    Direction,
    LandmarkKind,
    PairSuggestion,
    ProposalState,
    TravelMode,
    TravelRequest,
    TravelRequestStatus,
)
from app.models.user_model import User
from app.schemas import campus_schema

logger = logging.getLogger(__name__)

# Per-call cap on rows handled by expire_stale; a backlog drains over later calls.
EXPIRE_BATCH_LIMIT = 500

_OPEN = TravelRequestStatus.OPEN
_RESERVED = TravelRequestStatus.RESERVED
_LIVE_STATUSES = (TravelRequestStatus.OPEN, TravelRequestStatus.RESERVED)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------
def conflict(code: str, message: str, current: Optional[dict] = None) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": code, "message": message, "current": current or {}},
    )


def invalid(code: str, message: Optional[str] = None) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message or code})


def request_view(row: TravelRequest) -> dict:
    return campus_schema.TravelRequestOut.from_request(row).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Lazy expiry
# ---------------------------------------------------------------------------
def expire_stale(db: Session, now: datetime) -> int:
    """Mark overdue rows EXPIRED. Returns the number of rows changed.

    - OPEN requests with ``expires_at <= now`` -> EXPIRED (version + 1);
    - PENDING proposals with ``expires_at <= now``, or touching a request that
      was just expired -> EXPIRED (version + 1, resolved_at = now).

    Commit-free: callers commit. Rows currently locked by another transaction
    are skipped (SKIP LOCKED on PostgreSQL) and picked up by a later call, so
    this never waits on, or deadlocks with, a concurrent accept.
    """
    now_db = campus_time.to_db(now)
    changed = 0

    stale_ids = [
        r.id
        for r in db.query(TravelRequest.id)
        .filter(TravelRequest.status == _OPEN, TravelRequest.expires_at <= now_db)
        .order_by(TravelRequest.id)
        .limit(EXPIRE_BATCH_LIMIT)
        .with_for_update(skip_locked=True)
        .all()
    ]
    if stale_ids:
        rows = (
            db.query(TravelRequest)
            .filter(TravelRequest.id.in_(stale_ids), TravelRequest.status == _OPEN)
            .order_by(TravelRequest.id)
            .populate_existing()
            .all()
        )
        for row in rows:
            row.status = TravelRequestStatus.EXPIRED
            row.version = (row.version or 0) + 1
            changed += 1

    pending = (
        db.query(ConnectionProposal)
        .filter(ConnectionProposal.state == ProposalState.PENDING)
        .filter(
            or_(
                ConnectionProposal.expires_at <= now_db,
                ConnectionProposal.proposer_request_id.in_(stale_ids or [-1]),
                ConnectionProposal.recipient_request_id.in_(stale_ids or [-1]),
            )
        )
        .order_by(ConnectionProposal.id)
        .limit(EXPIRE_BATCH_LIMIT)
        .with_for_update(skip_locked=True)
        .populate_existing()
        .all()
    )
    for proposal in pending:
        proposal.state = ProposalState.EXPIRED
        proposal.version = (proposal.version or 0) + 1
        proposal.resolved_at = now_db
        changed += 1

    if changed:
        db.flush()
    return changed


def invalidate_request_connections(db: Session, request_id: int, now: datetime) -> dict:
    """Expire PENDING proposals touching the request and delete its suggestions.

    The caller already holds the request row lock. Commit-free. Proposals keep
    their history; only their ``suggestion_id`` link is cleared when the
    suggestion row is deleted. Returns counts.
    """
    now_db = campus_time.to_db(now)
    proposals = (
        db.query(ConnectionProposal)
        .filter(
            ConnectionProposal.state == ProposalState.PENDING,
            or_(
                ConnectionProposal.proposer_request_id == request_id,
                ConnectionProposal.recipient_request_id == request_id,
            ),
        )
        .order_by(ConnectionProposal.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    for proposal in proposals:
        proposal.state = ProposalState.EXPIRED
        proposal.version = (proposal.version or 0) + 1
        proposal.resolved_at = now_db

    suggestion_ids = [
        s.id
        for s in db.query(PairSuggestion.id).filter(
            or_(
                PairSuggestion.request_low_id == request_id,
                PairSuggestion.request_high_id == request_id,
            )
        )
    ]
    deleted = 0
    if suggestion_ids:
        db.flush()
        db.query(ConnectionProposal).filter(
            ConnectionProposal.suggestion_id.in_(suggestion_ids)
        ).update({ConnectionProposal.suggestion_id: None}, synchronize_session=False)
        deleted = (
            db.query(PairSuggestion)
            .filter(PairSuggestion.id.in_(suggestion_ids))
            .delete(synchronize_session=False)
        )
    db.flush()
    return {"proposals_expired": len(proposals), "suggestions_deleted": deleted}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def list_landmarks(db: Session, user: User) -> List[CampusLandmark]:
    if user.college_id is None:
        return []
    return (
        db.query(CampusLandmark)
        .filter(CampusLandmark.college_id == user.college_id, CampusLandmark.active.is_(True))
        .order_by(CampusLandmark.kind, CampusLandmark.name)
        .all()
    )


def list_requests(db: Session, user: User, status: Optional[str]) -> List[TravelRequest]:
    query = db.query(TravelRequest).filter(TravelRequest.user_id == user.id)
    if status is not None:
        try:
            query = query.filter(TravelRequest.status == TravelRequestStatus(status.upper()))
        except ValueError:
            raise invalid("invalid_status", f"unknown status {status!r}")
    return query.order_by(TravelRequest.id.desc()).all()


def get_own_request(db: Session, user: User, request_id: int, lock: bool = False) -> TravelRequest:
    """The caller's request, or 404 (also when it belongs to someone else)."""
    query = db.query(TravelRequest).filter(
        TravelRequest.id == request_id, TravelRequest.user_id == user.id
    )
    if lock:
        query = query.populate_existing().with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def _find_overlap(
    db: Session,
    user_id: int,
    origin_id: int,
    hub_id: int,
    direction: Direction,
    earliest_db: datetime,
    latest_db: datetime,
    exclude_id: Optional[int] = None,
) -> Optional[TravelRequest]:
    query = db.query(TravelRequest).filter(
        TravelRequest.user_id == user_id,
        TravelRequest.origin_landmark_id == origin_id,
        TravelRequest.hub_id == hub_id,
        TravelRequest.direction == direction,
        TravelRequest.status.in_(_LIVE_STATUSES),
        TravelRequest.earliest_departure <= latest_db,
        TravelRequest.latest_departure >= earliest_db,
    )
    if exclude_id is not None:
        query = query.filter(TravelRequest.id != exclude_id)
    return query.order_by(TravelRequest.id).first()


def _lock_user(db: Session, user: User) -> None:
    """Serialise create/edit by one user (row lock; a no-op on SQLite)."""
    db.query(User.id).filter(User.id == user.id).with_for_update().first()


def create_request(
    db: Session, user: User, body: campus_schema.TravelRequestCreate, now: datetime
) -> TravelRequest:
    if user.college_id is None:
        raise invalid("college_required", "Your account has no college")

    origin = db.query(CampusLandmark).filter(CampusLandmark.id == body.origin_landmark_id).first()
    hub = db.query(CampusLandmark).filter(CampusLandmark.id == body.hub_id).first()
    for landmark, kind, code in (
        (origin, LandmarkKind.CAMPUS_POINT, "invalid_origin_landmark"),
        (hub, LandmarkKind.HUB, "invalid_hub_landmark"),
    ):
        if (
            landmark is None
            or landmark.college_id != user.college_id
            or not landmark.active
            or landmark.kind != kind
        ):
            raise invalid(code, f"{code}: must be an active {kind.value} of your college")

    try:
        campus_rules.validate_window(body.earliest_departure, body.latest_departure, now)
    except ValueError as exc:
        raise invalid(str(exc))
    if body.arrive_by is not None and body.arrive_by <= body.earliest_departure:
        raise invalid("arrive_by_before_window", "arrive_by must be after the earliest departure")

    expires_at = campus_rules.resolve_request_expiry(body.latest_departure, body.expires_at)
    if expires_at <= now:
        raise invalid("invalid_expires_at", "expires_at must be in the future")

    _lock_user(db, user)
    expire_stale(db, now)

    direction = Direction(body.direction)
    earliest_db = campus_time.to_db(body.earliest_departure)
    latest_db = campus_time.to_db(body.latest_departure)

    clash = _find_overlap(db, user.id, origin.id, hub.id, direction, earliest_db, latest_db)
    if clash is not None:
        raise conflict(
            "overlapping_request",
            "You already have a request on this route with an overlapping departure window",
            {"request": request_view(clash)},
        )
    live = (
        db.query(TravelRequest)
        .filter(TravelRequest.user_id == user.id, TravelRequest.status.in_(_LIVE_STATUSES))
        .count()
    )
    if live >= campus_rules.MAX_OPEN_REQUESTS_PER_USER:
        raise conflict(
            "max_open_requests",
            f"You can have at most {campus_rules.MAX_OPEN_REQUESTS_PER_USER} open requests",
            {"limit": campus_rules.MAX_OPEN_REQUESTS_PER_USER},
        )

    row = TravelRequest(
        user_id=user.id,
        college_id=user.college_id,
        mode=TravelMode.SHARED_TAXI_PARTY,
        origin_landmark_id=origin.id,
        hub_id=hub.id,
        direction=direction,
        earliest_departure=earliest_db,
        latest_departure=latest_db,
        arrive_by=campus_time.to_db(body.arrive_by) if body.arrive_by is not None else None,
        timezone=body.timezone,
        flexibility_consent=bool(body.flexibility_consent),
        expires_at=campus_time.to_db(expires_at),
        status=_OPEN,
        version=1,
        created_at=campus_time.to_db(now),
        updated_at=campus_time.to_db(now),
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Edit / cancel
# ---------------------------------------------------------------------------
def patch_request(
    db: Session, user: User, request_id: int, body: campus_schema.TravelRequestPatch, now: datetime
) -> TravelRequest:
    # Same lock order as create_request (user row, then request row) so concurrent
    # creates/edits by one user serialise before the overlap re-check.
    _lock_user(db, user)
    row = get_own_request(db, user, request_id, lock=True)
    expire_stale(db, now)
    if row.status != _OPEN:
        raise conflict(
            "request_not_open",
            f"Only OPEN requests can be edited (this one is {row.status.value})",
            {"request": request_view(row)},
        )
    if body.expected_version != row.version:
        raise conflict(
            "stale_version",
            "The request changed since you loaded it",
            {"request": request_view(row)},
        )

    provided = body.model_fields_set - {"expected_version"}
    # Explicit nulls for the window fields / flexibility mean "unchanged"; only
    # arrive_by treats null as "clear the deadline".
    earliest = (
        body.earliest_departure
        if "earliest_departure" in provided and body.earliest_departure is not None
        else campus_time.from_db(row.earliest_departure)
    )
    latest = (
        body.latest_departure
        if "latest_departure" in provided and body.latest_departure is not None
        else campus_time.from_db(row.latest_departure)
    )
    if "arrive_by" in provided:
        arrive_by = body.arrive_by
    else:
        arrive_by = campus_time.from_db(row.arrive_by) if row.arrive_by is not None else None
    flex = (
        bool(body.flexibility_consent)
        if "flexibility_consent" in provided and body.flexibility_consent is not None
        else bool(row.flexibility_consent)
    )

    earliest_db, latest_db = campus_time.to_db(earliest), campus_time.to_db(latest)
    arrive_by_db = campus_time.to_db(arrive_by) if arrive_by is not None else None
    if (
        earliest_db == row.earliest_departure
        and latest_db == row.latest_departure
        and arrive_by_db == row.arrive_by
        and flex == bool(row.flexibility_consent)
    ):
        return row  # nothing changes: no version bump, no proposal expiry

    try:
        campus_rules.validate_window(earliest, latest, now)
    except ValueError as exc:
        raise invalid(str(exc))
    if arrive_by is not None and arrive_by <= earliest:
        raise invalid("arrive_by_before_window", "arrive_by must be after the earliest departure")

    clash = _find_overlap(
        db, user.id, row.origin_landmark_id, row.hub_id, row.direction,
        earliest_db, latest_db, exclude_id=row.id,
    )
    if clash is not None:
        raise conflict(
            "overlapping_request",
            "You already have a request on this route with an overlapping departure window",
            {"request": request_view(clash)},
        )

    if latest_db != row.latest_departure:
        row.expires_at = campus_time.to_db(campus_rules.resolve_request_expiry(latest, None))
    row.earliest_departure = earliest_db
    row.latest_departure = latest_db
    row.arrive_by = arrive_by_db
    row.flexibility_consent = flex
    row.version = row.version + 1
    row.updated_at = campus_time.to_db(now)

    invalidate_request_connections(db, row.id, now)
    db.flush()
    return row


def cancel_request(db: Session, user: User, request_id: int, now: datetime) -> TravelRequest:
    row = get_own_request(db, user, request_id, lock=True)
    expire_stale(db, now)
    if row.status == _RESERVED:
        raise conflict(
            "use_party_cancel",
            "This request is part of an agreed party; cancel the party instead",
            {"request": request_view(row)},
        )
    if row.status != _OPEN:
        return row  # already terminal: idempotent
    row.status = TravelRequestStatus.CANCELLED
    row.version = row.version + 1
    row.updated_at = campus_time.to_db(now)
    invalidate_request_connections(db, row.id, now)
    db.flush()
    return row
