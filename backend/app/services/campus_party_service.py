# backend/app/services/campus_party_service.py
"""Connections (proposals) and parties for campus shared-taxi coordination.

Lock order (ONE global order across all campus code; never acquire an earlier
level after a later one in the same transaction):
  1. user rows, ascending id (FOR NO KEY UPDATE; only accept takes them here)
  2. travel_request rows, ascending id (FOR UPDATE)
  3. the travel_party row
  4. party members, proposals, changes and everything else
Paths that never lock users (create proposal, decline/withdraw, cancel, report,
changes, note) start at level 2 or 3 and so never take a user lock afterwards.

Concurrency discipline (same as pooling_service):
- lock every involved TravelRequest row with SELECT ... FOR UPDATE in ASCENDING
  id order first, then the party row, then its members; proposal / change /
  event rows are only touched afterwards;
- re-read and decide under the lock (``populate_existing``);
- one transaction per state change (state + event + outbox rows + idempotency
  record), COMMIT, and only then best-effort notifications.
  Notification failures never change committed state.
- the partial unique indexes ("one active party per user", "a request is in at
  most one active party", "one PENDING proposal per pair", "one PENDING change
  per party") are the last line of defence: an IntegrityError rolls back and is
  turned into a clean 409 built from fresh state.

A party is a participant agreement. It is not a booking, a dispatch or a safety
guarantee; completion is self-reported.

409 ``current`` payloads only contain state the caller may see: the proposal the
caller is on and the caller's OWN active party (or null). Another user's party
is never exposed to a non-member.
"""

import copy
import functools
import logging
from datetime import timedelta
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, joinedload

from app.core import campus_rules, campus_time
from app.core.ws_manager import manager
from app.models.user_model import User
from app.models.campus_model import (
    CampusLandmark,
    ChangeState,
    ConnectionProposal,
    LandmarkKind,
    PairSuggestion,
    PartyChangeProposal,
    PartyEventType,
    PartyMember,
    PartyState,
    ProposalState,
    ReportOutcome,
    TravelParty,
    TravelRequest,
    TravelRequestStatus,
)
from app.schemas import campus_schema as schemas
from app.services import campus_events, campus_idempotency, campus_outbox

logger = logging.getLogger(__name__)

MAX_DB_INT = 2_147_483_647  # ids beyond a 32-bit INTEGER can never exist

# end_reason codes
END_CANCELLED = "cancelled_by_member"
END_COMPLETED = "completed"
END_DID_NOT_HAPPEN = "did_not_happen"
END_DISPUTED = "disputed"


@dataclass
class Result:
    """A JSON-able response body; ``replay`` marks an idempotent replay."""

    body: Any
    replay: bool = False


# ==========================================================================
# helpers
# ==========================================================================
def _err(status: int, code: str, message: str, current: Optional[dict] = None) -> HTTPException:
    detail: Dict[str, Any] = {"code": code, "message": message}
    if status == 409:
        detail["current"] = current or {}
    elif current:
        detail["current"] = current
    return HTTPException(status_code=status, detail=detail)


def _lock_requests(db: Session, request_ids) -> Dict[int, TravelRequest]:
    """SELECT ... FOR UPDATE in ascending id order (the deadlock-avoidance rule)."""
    ids = sorted({i for i in request_ids if i is not None})
    if not ids:
        return {}
    rows = (
        db.query(TravelRequest)
        .filter(TravelRequest.id.in_(ids))
        .order_by(TravelRequest.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    return {r.id: r for r in rows}


def _lock_party(db: Session, party_id: int) -> Optional[TravelParty]:
    return (
        db.query(TravelParty)
        .filter(TravelParty.id == party_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def _lock_members(db: Session, party_id: int) -> List[PartyMember]:
    return (
        db.query(PartyMember)
        .filter(PartyMember.party_id == party_id)
        .order_by(PartyMember.id)
        .populate_existing()
        .with_for_update()
        .all()
    )


def _lock_users(db: Session, user_ids) -> None:
    """Lock the participants' user rows in ASCENDING id order (FOR NO KEY UPDATE, so
    foreign-key inserts that only take KEY SHARE are not blocked). Serialises
    accepts that share a student even when their request locks are disjoint, which
    is what prevents the cross-accept deadlock on the party_members unique indexes."""
    ids = sorted({i for i in user_ids if i is not None})
    if ids:
        db.query(User.id).filter(User.id.in_(ids)).order_by(User.id).with_for_update(
            key_share=True
        ).all()


def _strip_contacts(body):
    """Defensive copy of a stored body with partner phone/email removed."""
    return campus_idempotency.sanitize_body(body)


def _fresh_replay(db: Session, uid: int, op: str, stored):
    """Idempotent replay: same status, no new event/party, but the VIEW is rebuilt
    from CURRENT state for the replaying user, so partner contact details are only
    present while the party is still AGREED."""
    try:
        if op == campus_idempotency.OP_ACCEPT_CONNECTION:
            proposal = (
                db.query(ConnectionProposal)
                .filter(ConnectionProposal.id == stored["connection"]["id"])
                .populate_existing().one_or_none()
            )
            party = (
                db.query(TravelParty)
                .filter(TravelParty.id == stored["party"]["id"])
                .populate_existing().one_or_none()
            )
            if proposal is not None and party is not None and _membership(db, party.id, uid):
                return {"connection": _proposal_dict(proposal, uid),
                        "party": _party_dict(db, party, uid)}
        else:
            party = (
                db.query(TravelParty).filter(TravelParty.id == stored["id"])
                .populate_existing().one_or_none()
            )
            if party is not None and _membership(db, party.id, uid):
                return _party_dict(db, party, uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not rebuild idempotent replay view: %s", type(exc).__name__)
    return _strip_contacts(stored)


def _now():
    now = campus_time.utcnow()
    return now, campus_time.to_db(now)


def _proposal_dict(p: ConnectionProposal, viewer_id: int) -> dict:
    return schemas.ConnectionOut.from_proposal(p, viewer_id).model_dump(mode="json")


def _pending_change(db: Session, party_id: int) -> Optional[PartyChangeProposal]:
    return (
        db.query(PartyChangeProposal)
        .filter(
            PartyChangeProposal.party_id == party_id,
            PartyChangeProposal.state == ChangeState.PENDING,
        )
        .populate_existing()
        .first()
    )


def _party_dict(db: Session, party: TravelParty, viewer_id: int) -> dict:
    db.flush()
    change = _pending_change(db, party.id)
    return schemas.PartyOut.from_party(party, viewer_id, change).model_dump(mode="json")


def _active_party_dict(db: Session, user_id: int) -> Optional[dict]:
    """The caller's OWN AGREED party (never anybody else's)."""
    party = (
        db.query(TravelParty)
        .join(PartyMember, PartyMember.party_id == TravelParty.id)
        .filter(
            PartyMember.user_id == user_id,
            PartyMember.active.is_(True),
            TravelParty.state == PartyState.AGREED,
        )
        .first()
    )
    return _party_dict(db, party, user_id) if party is not None else None


def _busy_users(db: Session, user_ids) -> List[int]:
    rows = (
        db.query(PartyMember.user_id)
        .filter(PartyMember.user_id.in_(list(user_ids)), PartyMember.active.is_(True))
        .all()
    )
    return [r[0] for r in rows]


def _precheck_busy(db: Session, user_ids) -> List[int]:
    """Ordered-check variant of ``_busy_users`` (kept separate so the post-race
    fallback always consults the database for real)."""
    return _busy_users(db, user_ids)


def _membership(db: Session, party_id: int, user_id: int) -> Optional[PartyMember]:
    return (
        db.query(PartyMember)
        .filter(PartyMember.party_id == party_id, PartyMember.user_id == user_id)
        .first()
    )


def _party_404() -> HTTPException:
    return HTTPException(status_code=404, detail="Party not found")


async def _send(user_id: int, message: dict) -> None:
    """Best-effort socket push. Never raises."""
    try:
        await manager.send_personal_message(message, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("campus notification failed (type=%s): %s", message.get("type"), type(exc).__name__)


async def _dispatch(db: Session, party_id: int) -> None:
    """Best-effort outbox dispatch AFTER the commit; never raises, never changes state."""
    try:
        await campus_outbox.dispatch_for_party(db, party_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("outbox dispatch failed for party %s: %s", party_id, type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _current_party_state(db: Session, uid: int, party_id) -> dict:
    """The caller's authorized view of a party (empty when not a member)."""
    try:
        if _membership(db, party_id, uid) is None:
            return {}
        party = db.query(TravelParty).filter(TravelParty.id == party_id).populate_existing().one()
        return {"party": _party_dict(db, party, uid)}
    except Exception:  # noqa: BLE001
        db.rollback()
        return {}


def _current_proposal_state(db: Session, uid: int, proposal_id) -> dict:
    try:
        p = db.query(ConnectionProposal).filter(ConnectionProposal.id == proposal_id).populate_existing().first()
        if p is None or uid not in (p.proposer_id, p.recipient_id):
            return {}
        return {"proposal": _proposal_dict(p, uid), "active_party": _active_party_dict(db, uid)}
    except Exception:  # noqa: BLE001
        db.rollback()
        return {}


def _current_own_state(db: Session, uid: int, _target) -> dict:
    try:
        return {"active_party": _active_party_dict(db, uid)}
    except Exception:  # noqa: BLE001
        db.rollback()
        return {}


def retry_on_deadlock(current, fallback=None):
    """Decorator for the service entry points ``fn(db, user, target_id, ...)``.

    A Postgres deadlock / serialization failure surfaces as ``OperationalError``.
    It means we lost a race, nothing was committed: roll back and run the WHOLE
    operation once more (it re-reads everything under its locks). If it happens
    again, never 500: ``fallback(db, user, *args, **kwargs)`` when given (accept ->
    participant_busy) or 409 ``conflict_retry`` whose ``current`` is the caller's
    authorized view built by ``current(db, user_id, target_id)``.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(db, user, *args, **kwargs):
            uid = user.id
            for attempt in (0, 1):
                try:
                    return await fn(db, user, *args, **kwargs)
                except OperationalError:
                    db.rollback()
                    logger.warning("%s: deadlock/serialization failure (attempt %s)", fn.__name__, attempt + 1)
            if fallback is not None:
                return fallback(db, user, *args, **kwargs)
            target = args[0] if args else None
            raise _err(409, "conflict_retry",
                       "The server was busy with a competing change; please retry.",
                       current(db, uid, target))

        return wrapper

    return decorator


def _expire_overdue_proposals(
    db: Session,
    now,
    *,
    request_ids=None,
    user_id: Optional[int] = None,
) -> int:
    """Lazily mark PENDING proposals whose expires_at has passed as EXPIRED.

    Scoped (to proposals touching ``request_ids`` -- which the caller has locked
    -- or involving ``user_id``) so we never touch rows other transactions are
    entitled to. Does not commit.
    """
    now_db = campus_time.to_db(now)
    stmt = update(ConnectionProposal).where(
        ConnectionProposal.state == ProposalState.PENDING,
        ConnectionProposal.expires_at <= now_db,
    )
    if request_ids:
        ids = list(request_ids)
        stmt = stmt.where(
            or_(
                ConnectionProposal.proposer_request_id.in_(ids),
                ConnectionProposal.recipient_request_id.in_(ids),
            )
        )
    if user_id is not None:
        stmt = stmt.where(
            or_(ConnectionProposal.proposer_id == user_id, ConnectionProposal.recipient_id == user_id)
        )
    stmt = stmt.values(
        state=ProposalState.EXPIRED,
        resolved_at=now_db,
        version=ConnectionProposal.version + 1,
    ).execution_options(synchronize_session=False)
    result = db.execute(stmt)
    return result.rowcount or 0


# ==========================================================================
# Connections
# ==========================================================================
@retry_on_deadlock(_current_own_state)
async def create_proposal(
    db: Session, user, suggestion_id: int, body: schemas.ConnectionCreate
) -> Result:
    uid = user.id
    now, now_db = _now()
    suggestion = db.get(PairSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    low_id, high_id = suggestion.request_low_id, suggestion.request_high_id
    owners = {
        r.id: r.user_id
        for r in db.query(TravelRequest).filter(TravelRequest.id.in_([low_id, high_id])).all()
    }
    if uid not in owners.values():
        raise HTTPException(status_code=404, detail="Suggestion not found")

    notify = None
    try:
        locked = _lock_requests(db, [low_id, high_id])
        req_low, req_high = locked.get(low_id), locked.get(high_id)
        suggestion = (
            db.query(PairSuggestion)
            .filter(PairSuggestion.id == suggestion_id)
            .populate_existing()
            .one_or_none()
        )
        if suggestion is None or req_low is None or req_high is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        mine = req_low if req_low.user_id == uid else req_high
        other = req_high if mine is req_low else req_low

        _expire_overdue_proposals(db, now, request_ids=[low_id, high_id])

        elig = campus_rules.eligible_pair(req_low, req_high, now)
        if not elig.ok:
            raise _err(409, "not_eligible", "These requests can no longer be paired.",
                       {"reason": elig.reason})

        duplicate = (
            db.query(ConnectionProposal)
            .filter(
                ConnectionProposal.pair_low_request_id == low_id,
                ConnectionProposal.pair_high_request_id == high_id,
                ConnectionProposal.state == ProposalState.PENDING,
            )
            .populate_existing()
            .first()
        )
        if duplicate is not None:
            raise _err(409, "duplicate_proposal", "A proposal for this pair is already pending.",
                       {"proposal": _proposal_dict(duplicate, uid)})

        warnings = list(suggestion.warnings or [])
        if warnings and not body.acknowledge_warnings:
            raise _err(409, "warnings_unacknowledged",
                       "This match has warnings that must be acknowledged.",
                       {"warnings": warnings})

        proposal = ConnectionProposal(
            suggestion_id=suggestion.id,
            proposer_id=uid,
            recipient_id=other.user_id,
            proposer_request_id=mine.id,
            recipient_request_id=other.id,
            proposer_request_version=mine.version,
            recipient_request_version=other.version,
            state=ProposalState.PENDING,
            expires_at=campus_time.to_db(campus_rules.proposal_expires_at(now, req_low, req_high)),
            version=1,
            created_at=now_db,
        )
        db.add(proposal)
        db.flush()
        out = _proposal_dict(proposal, uid)
        notify = (other.user_id, {
            "type": "connection_proposed",
            "proposal": _proposal_dict(proposal, other.user_id),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        dup = (
            db.query(ConnectionProposal)
            .filter(
                ConnectionProposal.pair_low_request_id == low_id,
                ConnectionProposal.pair_high_request_id == high_id,
                ConnectionProposal.state == ProposalState.PENDING,
            )
            .first()
        )
        if dup is None:
            raise
        raise _err(409, "duplicate_proposal", "A proposal for this pair is already pending.",
                   {"proposal": _proposal_dict(dup, uid)})
    except Exception:
        db.rollback()
        raise

    await _send(*notify)
    return Result(out)


def list_proposals(
    db: Session, user, role: str = "all", state: Optional[str] = None, limit: int = 100
) -> List[dict]:
    limit = max(1, min(int(limit), 200))
    uid = user.id
    if role not in ("incoming", "outgoing", "all"):
        raise HTTPException(status_code=422, detail="role must be incoming, outgoing or all")
    state_enum = None
    if state:
        try:
            state_enum = ProposalState(state.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid state filter")
    now, _ = _now()
    try:
        if _expire_overdue_proposals(db, now, user_id=uid):
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    q = db.query(ConnectionProposal).options(
        joinedload(ConnectionProposal.proposer),
        joinedload(ConnectionProposal.recipient),
        joinedload(ConnectionProposal.proposer_request),
    ).populate_existing()
    if role == "incoming":
        q = q.filter(ConnectionProposal.recipient_id == uid)
    elif role == "outgoing":
        q = q.filter(ConnectionProposal.proposer_id == uid)
    else:
        q = q.filter(or_(ConnectionProposal.recipient_id == uid, ConnectionProposal.proposer_id == uid))
    if state_enum is not None:
        q = q.filter(ConnectionProposal.state == state_enum)
    rows = q.order_by(ConnectionProposal.id.desc()).limit(limit).all()
    return [_proposal_dict(p, uid) for p in rows]


def _accept_conflict(
    db: Session, uid: int, proposal: ConnectionProposal, code: str, message: str
) -> HTTPException:
    """409 whose ``current`` is ONLY the caller's view: the proposal as it is now
    plus the caller's own active party (or null) -- never a winner's party."""
    db.flush()
    current = {
        "proposal": _proposal_dict(proposal, uid),
        "active_party": _active_party_dict(db, uid),
    }
    return _err(409, code, message, current)


def _accept_busy_fallback(db: Session, user, proposal_id: int, body: schemas.ConnectionAccept) -> Result:
    return _accept_integrity_fallback(db, user.id, proposal_id, body, None, force=True)


@retry_on_deadlock(_current_proposal_state, fallback=_accept_busy_fallback)
async def accept_proposal(
    db: Session, user, proposal_id: int, body: schemas.ConnectionAccept
) -> Result:
    uid = user.id
    op = campus_idempotency.OP_ACCEPT_CONNECTION
    now, now_db = _now()

    replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, proposal_id)
    if replay is not None:
        return Result(_fresh_replay(db, uid, op, replay), True)

    head = db.get(ConnectionProposal, proposal_id)
    if head is None or head.recipient_id != uid:
        raise HTTPException(status_code=404, detail="Connection not found")
    req_ids = [head.proposer_request_id, head.recipient_request_id]
    party_id = None

    try:
        # Global lock order: user rows first, then request rows.
        _lock_users(db, [head.proposer_id, head.recipient_id])
        locked = _lock_requests(db, req_ids)

        # A concurrent request with the same key may have committed meanwhile.
        replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, proposal_id)
        if replay is not None:
            fresh = _fresh_replay(db, uid, op, replay)
            db.rollback()
            return Result(fresh, True)

        proposal = (
            db.query(ConnectionProposal)
            .filter(ConnectionProposal.id == proposal_id)
            .populate_existing()
            .one()
        )
        req_p = locked[proposal.proposer_request_id]
        req_r = locked[proposal.recipient_request_id]

        # ---- ordered 409 checks ------------------------------------------
        if proposal.state != ProposalState.PENDING:
            raise _accept_conflict(db, uid, proposal, "already_resolved",
                                   "This connection has already been resolved.")
        if campus_time.from_db(proposal.expires_at) <= now:
            proposal.state = ProposalState.EXPIRED
            proposal.version += 1
            proposal.resolved_at = now_db
            exc = _accept_conflict(db, uid, proposal, "expired", "This connection has expired.")
            db.commit()
            raise exc
        if body.expected_version != proposal.version:
            raise _accept_conflict(db, uid, proposal, "stale_version",
                                   "This connection changed; reload and try again.")
        if (
            req_p.status != TravelRequestStatus.OPEN
            or req_r.status != TravelRequestStatus.OPEN
            or req_p.version != proposal.proposer_request_version
            or req_r.version != proposal.recipient_request_version
        ):
            raise _accept_conflict(db, uid, proposal, "request_changed",
                                   "One of the travel requests changed after this proposal.")
        elig = campus_rules.eligible_pair(req_p, req_r, now)
        if not elig.ok:
            raise _accept_conflict(db, uid, proposal, "not_eligible",
                                   "These requests can no longer be paired.")
        if _precheck_busy(db, [proposal.proposer_id, proposal.recipient_id]):
            raise _accept_conflict(db, uid, proposal, "participant_busy",
                                   "A participant is already in an active party.")
        departure = campus_rules.agreed_departure(elig.feasible_start, elig.feasible_end, now)
        if departure is None:
            raise _accept_conflict(db, uid, proposal, "window_closed",
                                   "The shared departure window has closed.")

        # ---- success path: ONE transaction --------------------------------
        meeting = db.get(CampusLandmark, req_p.origin_landmark_id)
        party = TravelParty(
            state=PartyState.AGREED,
            agreed_departure=campus_time.to_db(departure),
            meeting_landmark_id=req_p.origin_landmark_id,
            hub_id=req_p.hub_id,
            direction=req_p.direction,
            timezone=(meeting.timezone if meeting is not None else req_p.timezone),
            transport_responsibility=campus_rules.TRANSPORT_RESPONSIBILITY_TEXT,
            version=0,
            created_at=now_db,
        )
        db.add(party)
        db.flush()
        party_id = party.id
        # Insert the member rows in ASCENDING user_id order so two transactions that
        # touch the same two students can never wait on each other's unique-index
        # entries in opposite orders (deadlock).
        pairs = sorted(
            [(proposal.proposer_id, req_p.id), (proposal.recipient_id, req_r.id)]
        )
        for member_user_id, member_request_id in pairs:
            db.add(PartyMember(party_id=party_id, user_id=member_user_id,
                               request_id=member_request_id, active=True))
            db.flush()  # the partial unique indexes decide a race here

        proposal.state = ProposalState.ACCEPTED
        proposal.version += 1
        proposal.party_id = party_id
        proposal.resolved_at = now_db
        for r in (req_p, req_r):
            r.status = TravelRequestStatus.RESERVED
            r.version += 1

        others = (
            db.query(ConnectionProposal)
            .filter(
                ConnectionProposal.id != proposal.id,
                ConnectionProposal.state == ProposalState.PENDING,
                or_(
                    ConnectionProposal.proposer_request_id.in_(req_ids),
                    ConnectionProposal.recipient_request_id.in_(req_ids),
                ),
            )
            .order_by(ConnectionProposal.id)
            .populate_existing()
            .with_for_update()
            .all()
        )
        for other in others:
            other.state = ProposalState.EXPIRED
            other.version += 1
            other.resolved_at = now_db

        locked_party = _lock_party(db, party_id)  # no-op for a fresh row; keeps the rule uniform
        campus_events.record_party_event(
            db, locked_party or party, uid, PartyEventType.PARTY_AGREED,
            {
                "proposal_id": proposal.id,
                "agreed_departure": campus_time.utc_iso(party.agreed_departure),
                "member_ids": sorted([proposal.proposer_id, proposal.recipient_id]),
            },
            now,
        )
        db.flush()
        out = {
            "connection": _proposal_dict(proposal, uid),
            "party": _party_dict(db, party, uid),
        }
        campus_idempotency.store(db, uid, op, body.idempotency_key, proposal_id, 200, out)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        return _accept_integrity_fallback(db, uid, proposal_id, body, exc)
    except Exception:
        db.rollback()
        raise

    await _dispatch(db, party_id)
    return Result(out)


def _accept_integrity_fallback(
    db: Session, uid: int, proposal_id: int, body: schemas.ConnectionAccept, original: Exception,
    force: bool = False,
) -> Result:
    """A partial unique index (or the idempotency key) lost a race: rebuild a clean
    answer from fresh, committed state."""
    op = campus_idempotency.OP_ACCEPT_CONNECTION
    replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, proposal_id)
    if replay is not None:
        return Result(_fresh_replay(db, uid, op, replay), True)
    proposal = (
        db.query(ConnectionProposal)
        .filter(ConnectionProposal.id == proposal_id)
        .populate_existing()
        .one()
    )
    if proposal.state != ProposalState.PENDING:
        exc = _accept_conflict(db, uid, proposal, "already_resolved",
                               "This connection has already been resolved.")
    elif force or _busy_users(db, [proposal.proposer_id, proposal.recipient_id]):
        exc = _accept_conflict(db, uid, proposal, "participant_busy",
                               "A participant is already in an active party.")
    else:
        raise original
    db.rollback()
    raise exc


async def _resolve_proposal(
    db: Session, user, proposal_id: int, body: schemas.ConnectionDecision, *, action: str
) -> Result:
    """decline (recipient) / withdraw (proposer). Idempotent when already in the
    requested terminal state."""
    uid = user.id
    target = ProposalState.DECLINED if action == "decline" else ProposalState.WITHDRAWN
    now, now_db = _now()
    head = db.get(ConnectionProposal, proposal_id)
    if head is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    allowed = head.recipient_id if action == "decline" else head.proposer_id
    if allowed != uid:
        raise HTTPException(status_code=404, detail="Connection not found")
    notify = None
    try:
        _lock_requests(db, [head.proposer_request_id, head.recipient_request_id])
        proposal = (
            db.query(ConnectionProposal)
            .filter(ConnectionProposal.id == proposal_id)
            .populate_existing()
            .one()
        )
        if proposal.state == target:
            out = _proposal_dict(proposal, uid)
            db.rollback()
            return Result(out)
        if proposal.state != ProposalState.PENDING:
            raise _accept_conflict(db, uid, proposal, "already_resolved",
                                   "This connection has already been resolved.")
        if campus_time.from_db(proposal.expires_at) <= now:
            proposal.state = ProposalState.EXPIRED
            proposal.version += 1
            proposal.resolved_at = now_db
            exc = _accept_conflict(db, uid, proposal, "expired", "This connection has expired.")
            db.commit()
            raise exc
        if body.expected_version is not None and body.expected_version != proposal.version:
            raise _accept_conflict(db, uid, proposal, "stale_version",
                                   "This connection changed; reload and try again.")
        proposal.state = target
        proposal.version += 1
        proposal.resolved_at = now_db
        db.flush()
        out = _proposal_dict(proposal, uid)
        counterpart = proposal.proposer_id if action == "decline" else proposal.recipient_id
        notify = (counterpart, {
            "type": "connection_declined" if action == "decline" else "connection_withdrawn",
            "proposal": _proposal_dict(proposal, counterpart),
        })
        db.commit()
    except Exception:
        db.rollback()
        raise
    await _send(*notify)
    return Result(out)


@retry_on_deadlock(_current_proposal_state)
async def decline_proposal(db, user, proposal_id, body) -> Result:
    return await _resolve_proposal(db, user, proposal_id, body, action="decline")


@retry_on_deadlock(_current_proposal_state)
async def withdraw_proposal(db, user, proposal_id, body) -> Result:
    return await _resolve_proposal(db, user, proposal_id, body, action="withdraw")


# ==========================================================================
# Parties
# ==========================================================================
def get_party(db: Session, user, party_id: int) -> dict:
    uid = user.id
    if _membership(db, party_id, uid) is None:
        raise _party_404()
    party = db.query(TravelParty).filter(TravelParty.id == party_id).populate_existing().one()
    return _party_dict(db, party, uid)


def _party_conflict(db: Session, uid: int, party: TravelParty, code: str, message: str) -> HTTPException:
    return _err(409, code, message, {"party": _party_dict(db, party, uid)})


def _lost_race(db: Session, uid: int, party_id: int) -> HTTPException:
    """A unique index (e.g. the per-party event version) stopped a write that raced
    another one without the row locks; answer with a clean 409 from fresh state."""
    party = db.query(TravelParty).filter(TravelParty.id == party_id).populate_existing().one()
    return _party_conflict(db, uid, party, "stale_version", "The party changed; reload and try again.")


def _supersede_pending_change(db: Session, party_id: int, now_db) -> Optional[int]:
    change = _pending_change(db, party_id)
    if change is None:
        return None
    change.state = ChangeState.SUPERSEDED
    change.resolved_at = now_db
    return change.id


def _end_party(
    db: Session, party: TravelParty, members: List[PartyMember], now_db, end_reason: str, state: PartyState
) -> Optional[int]:
    party.state = state
    party.ended_at = now_db
    party.end_reason = end_reason
    for m in members:
        m.active = False
    return _supersede_pending_change(db, party.id, now_db)


@retry_on_deadlock(_current_party_state)
async def cancel_party(db: Session, user, party_id: int, body: schemas.PartyCancel) -> Result:
    uid = user.id
    op = campus_idempotency.OP_CANCEL_PARTY
    now, now_db = _now()

    replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, party_id)
    if replay is not None:
        return Result(_fresh_replay(db, uid, op, replay), True)
    if _membership(db, party_id, uid) is None:
        raise _party_404()

    try:
        request_ids = [
            m.request_id for m in db.query(PartyMember).filter(PartyMember.party_id == party_id).all()
        ]
        locked = _lock_requests(db, request_ids)
        party = _lock_party(db, party_id)
        members = _lock_members(db, party_id)

        replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, party_id)
        if replay is not None:
            fresh = _fresh_replay(db, uid, op, replay)
            db.rollback()
            return Result(fresh, True)

        if party.state == PartyState.CANCELLED:  # idempotent: no new event
            out = _party_dict(db, party, uid)
            db.rollback()
            return Result(out)
        if party.state != PartyState.AGREED:
            raise _party_conflict(db, uid, party, "party_not_cancellable",
                                  "A completed or disputed party cannot be cancelled.")
        if body.expected_version is not None and body.expected_version != party.version:
            raise _party_conflict(db, uid, party, "stale_version",
                                  "The party changed; reload and try again.")

        mine = next(m for m in members if m.user_id == uid)
        for m in members:
            req = locked.get(m.request_id)
            if req is None or req.status != TravelRequestStatus.RESERVED:
                continue
            if m is mine:
                req.status = TravelRequestStatus.CANCELLED
            elif req.expires_at > now_db and req.latest_departure > now_db:
                req.status = TravelRequestStatus.OPEN  # not re-matched automatically
            else:
                req.status = TravelRequestStatus.EXPIRED
            req.version += 1

        superseded = _end_party(db, party, members, now_db, END_CANCELLED, PartyState.CANCELLED)
        db.flush()
        payload = {"cancelled_by": uid, "end_reason": END_CANCELLED}
        if body.reason:
            payload["reason"] = body.reason
        if superseded is not None:
            payload["superseded_change_id"] = superseded
        campus_events.record_party_event(db, party, uid, PartyEventType.PARTY_CANCELLED, payload, now)
        out = _party_dict(db, party, uid)
        campus_idempotency.store(db, uid, op, body.idempotency_key, party_id, 200, out)
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = campus_idempotency.find_replay(db, uid, op, body.idempotency_key, party_id)
        if replay is not None:
            return Result(_fresh_replay(db, uid, op, replay), True)
        party = db.query(TravelParty).filter(TravelParty.id == party_id).populate_existing().one()
        if party.state == PartyState.CANCELLED:  # the other member's cancel won the race
            out = _party_dict(db, party, uid)
            db.rollback()
            return Result(out)
        raise
    except Exception:
        db.rollback()
        raise

    await _dispatch(db, party_id)
    return Result(out)


def _validate_departure_and_landmark(
    db: Session, party: TravelParty, departure, landmark_id: Optional[int], now
) -> None:
    if departure is not None:
        try:
            too_late = departure > now + timedelta(days=campus_rules.MAX_LEAD_DAYS)
            in_past = departure <= now
        except OverflowError:
            too_late, in_past = True, False
        if in_past:
            raise _err(422, "departure_in_past", "The new departure must be in the future.")
        if too_late:
            raise _err(422, "departure_out_of_range",
                       f"The new departure must be within {campus_rules.MAX_LEAD_DAYS} days.")
    if landmark_id is not None:
        if not 1 <= landmark_id <= MAX_DB_INT:
            raise _err(422, "invalid_landmark",
                       "The meeting point must be an active campus point of your college.")
        lm = db.get(CampusLandmark, landmark_id)
        current = db.get(CampusLandmark, party.meeting_landmark_id)
        if (
            lm is None
            or not lm.active
            or lm.kind != LandmarkKind.CAMPUS_POINT
            or current is None
            or lm.college_id != current.college_id
        ):
            raise _err(422, "invalid_landmark",
                       "The meeting point must be an active campus point of your college.")


@retry_on_deadlock(_current_party_state)
async def propose_change(
    db: Session, user, party_id: int, body: schemas.ChangeCreate
) -> Result:
    uid = user.id
    now, now_db = _now()
    if _membership(db, party_id, uid) is None:
        raise _party_404()
    try:
        party = _lock_party(db, party_id)
        if party.state != PartyState.AGREED:
            raise _party_conflict(db, uid, party, "party_not_active", "This party has ended.")
        if body.expected_version != party.version:
            raise _party_conflict(db, uid, party, "stale_version",
                                  "The party changed; reload and try again.")
        if body.agreed_departure is None and body.meeting_landmark_id is None:
            raise _err(422, "empty_change", "Propose a new departure time or meeting point.")
        if _pending_change(db, party_id) is not None:
            raise _party_conflict(db, uid, party, "change_pending",
                                  "Another change is already waiting for approval.")
        _validate_departure_and_landmark(db, party, body.agreed_departure, body.meeting_landmark_id, now)

        change = PartyChangeProposal(
            party_id=party_id,
            proposer_id=uid,
            new_departure=(campus_time.to_db(body.agreed_departure)
                           if body.agreed_departure is not None else None),
            new_meeting_landmark_id=body.meeting_landmark_id,
            note=body.note,
            expected_party_version=body.expected_version,
            state=ChangeState.PENDING,
            created_at=now_db,
        )
        db.add(change)
        db.flush()
        campus_events.record_party_event(
            db, party, uid, PartyEventType.CHANGE_PROPOSED,
            {
                "change_id": change.id,
                "new_departure": (campus_time.utc_iso(change.new_departure)
                                  if change.new_departure else None),
                "new_meeting_landmark_id": change.new_meeting_landmark_id,
            },
            now,
        )
        db.flush()
        db.refresh(change)
        out = schemas.ChangeOut.from_change(change, party.timezone).model_dump(mode="json")
        db.commit()
    except IntegrityError:
        db.rollback()
        party = db.get(TravelParty, party_id)
        raise _party_conflict(db, uid, party, "change_pending",
                              "Another change is already waiting for approval.")
    except Exception:
        db.rollback()
        raise
    await _dispatch(db, party_id)
    return Result(out)


def _load_change(db: Session, party_id: int, change_id: int) -> PartyChangeProposal:
    change = (
        db.query(PartyChangeProposal)
        .filter(PartyChangeProposal.id == change_id, PartyChangeProposal.party_id == party_id)
        .populate_existing()
        .first()
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return change


@retry_on_deadlock(_current_party_state)
async def decide_change(
    db: Session,
    user,
    party_id: int,
    change_id: int,
    *,
    action: str,
    expected_party_version: Optional[int] = None,
) -> Result:
    """approve / reject (the OTHER member) or withdraw (the proposer)."""
    uid = user.id
    now, now_db = _now()
    if _membership(db, party_id, uid) is None:
        raise _party_404()
    try:
        party = _lock_party(db, party_id)
        change = _load_change(db, party_id, change_id)

        if change.state != ChangeState.PENDING:
            raise _party_conflict(db, uid, party, "change_not_pending",
                                  "This change is no longer pending.")
        is_proposer = change.proposer_id == uid
        if action == "withdraw" and not is_proposer:
            raise _err(403, "not_proposer", "Only the proposer can withdraw a change.")
        if action in ("approve", "reject") and is_proposer:
            raise _err(403, "proposer_cannot_decide",
                       "The other member must approve or reject your change.")
        if party.state != PartyState.AGREED:
            raise _party_conflict(db, uid, party, "party_not_active", "This party has ended.")
        if expected_party_version is not None and expected_party_version != party.version:
            raise _party_conflict(db, uid, party, "stale_version",
                                  "The party changed; reload and try again.")

        change.resolved_at = now_db
        change.resolved_by = uid
        if action == "approve":
            _validate_still_applicable(db, party, change, uid, now)
            if change.new_departure is not None:
                party.agreed_departure = change.new_departure
            if change.new_meeting_landmark_id is not None:
                party.meeting_landmark_id = change.new_meeting_landmark_id
            change.state = ChangeState.APPROVED
            db.flush()
            db.expire(party, ["meeting_landmark"])
            etype, payload = PartyEventType.PARTY_CHANGED, {
                "change_id": change.id,
                "agreed_departure": campus_time.utc_iso(party.agreed_departure),
                "meeting_landmark_id": party.meeting_landmark_id,
            }
        elif action == "reject":
            change.state = ChangeState.REJECTED
            etype, payload = PartyEventType.CHANGE_REJECTED, {"change_id": change.id}
        else:
            change.state = ChangeState.WITHDRAWN
            # No dedicated event type exists: a withdrawal is reported as CHANGE_REJECTED
            # with withdrawn=true so the other member's client reconciles.
            etype, payload = PartyEventType.CHANGE_REJECTED, {
                "change_id": change.id, "withdrawn": True,
            }
        db.flush()
        campus_events.record_party_event(db, party, uid, etype, payload, now)
        db.flush()
        if action == "approve":
            out = _party_dict(db, party, uid)
        else:
            out = schemas.ChangeOut.from_change(change, party.timezone).model_dump(mode="json")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _lost_race(db, uid, party_id)
    except Exception:
        db.rollback()
        raise
    await _dispatch(db, party_id)
    return Result(out)


def _validate_still_applicable(db, party, change, uid, now) -> None:
    """Re-check a change at approval time (the world may have moved on)."""
    if change.new_departure is not None and campus_time.from_db(change.new_departure) <= now:
        raise _party_conflict(db, uid, party, "change_no_longer_valid",
                              "The proposed departure is already in the past.")
    if change.new_meeting_landmark_id is not None:
        try:
            _validate_departure_and_landmark(db, party, None, change.new_meeting_landmark_id, now)
        except HTTPException:
            raise _party_conflict(db, uid, party, "change_no_longer_valid",
                                  "The proposed meeting point is no longer valid.")


@retry_on_deadlock(_current_party_state)
async def update_cost_note(
    db: Session, user, party_id: int, body: schemas.PartyNotePatch
) -> Result:
    uid = user.id
    now, _ = _now()
    if _membership(db, party_id, uid) is None:
        raise _party_404()
    try:
        party = _lock_party(db, party_id)
        if party.state != PartyState.AGREED:
            raise _party_conflict(db, uid, party, "party_not_active", "This party has ended.")
        if body.expected_version != party.version:
            raise _party_conflict(db, uid, party, "stale_version",
                                  "The party changed; reload and try again.")
        party.cost_note = body.cost_note
        db.flush()
        campus_events.record_party_event(
            db, party, uid, PartyEventType.NOTE_UPDATED, {"field": "cost_note"}, now
        )
        out = _party_dict(db, party, uid)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _lost_race(db, uid, party_id)
    except Exception:
        db.rollback()
        raise
    await _dispatch(db, party_id)
    return Result(out)


@retry_on_deadlock(_current_party_state)
async def report_outcome(db: Session, user, party_id: int, body: schemas.ReportBody) -> Result:
    uid = user.id
    now, now_db = _now()
    outcome = ReportOutcome(body.outcome)
    if _membership(db, party_id, uid) is None:
        raise _party_404()
    try:
        request_ids = [
            m.request_id for m in db.query(PartyMember).filter(PartyMember.party_id == party_id).all()
        ]
        locked = _lock_requests(db, request_ids)
        party = _lock_party(db, party_id)
        members = _lock_members(db, party_id)
        mine = next(m for m in members if m.user_id == uid)

        if party.state != PartyState.AGREED:
            if mine.report_outcome == outcome:  # retry of the report that ended the party
                out = _party_dict(db, party, uid)
                db.rollback()
                return Result(out)
            raise _party_conflict(db, uid, party, "party_not_active", "This party has ended.")
        if now < campus_time.from_db(party.agreed_departure):
            raise _party_conflict(db, uid, party, "report_too_early",
                                  "You can report after the agreed departure time.")
        if mine.report_outcome == outcome:  # same report again: idempotent, no new event
            out = _party_dict(db, party, uid)
            db.rollback()
            return Result(out)

        mine.report_outcome = outcome
        mine.reported_at = now_db
        db.flush()
        # Blind reporting: the event (served to both members) never carries the
        # outcome; the actor is in PartyEvent.actor_id.
        campus_events.record_party_event(
            db, party, uid, PartyEventType.REPORT_RECORDED, {"reported": True}, now
        )

        if all(m.report_outcome is not None for m in members):
            outcomes = {m.report_outcome for m in members}
            if outcomes == {ReportOutcome.COMPLETED}:
                state, reason, etype = PartyState.COMPLETED, END_COMPLETED, PartyEventType.PARTY_COMPLETED
                req_status = TravelRequestStatus.FULFILLED
            elif outcomes == {ReportOutcome.DID_NOT_HAPPEN}:
                state, reason, etype = PartyState.CANCELLED, END_DID_NOT_HAPPEN, PartyEventType.PARTY_CANCELLED
                req_status = TravelRequestStatus.CANCELLED
            else:
                state, reason, etype = PartyState.DISPUTED, END_DISPUTED, PartyEventType.PARTY_DISPUTED
                req_status = TravelRequestStatus.CANCELLED
            for m in members:
                req = locked.get(m.request_id)
                if req is not None and req.status == TravelRequestStatus.RESERVED:
                    req.status = req_status
                    req.version += 1
            superseded = _end_party(db, party, members, now_db, reason, state)
            db.flush()
            payload = {"end_reason": reason}
            if superseded is not None:
                payload["superseded_change_id"] = superseded
            campus_events.record_party_event(db, party, uid, etype, payload, now)
        out = _party_dict(db, party, uid)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _lost_race(db, uid, party_id)
    except Exception:
        db.rollback()
        raise
    await _dispatch(db, party_id)
    return Result(out)
