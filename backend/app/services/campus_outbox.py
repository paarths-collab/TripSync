# backend/app/services/campus_outbox.py
"""Outbox dispatch for party events.

Callers commit state + event + outbox rows in ONE transaction and then call
``dispatch_for_party`` best-effort. Everything here is an *accelerator*: the
server state is authoritative and clients reconcile through REST, so no
function in this module ever raises and none ever touches party state.

Claiming. Two dispatchers (two workers, the background task plus a request,
a socket-connect flush) may run at once. Each due row is *claimed* with a
conditional ``UPDATE ... WHERE id = :id AND status = 'PENDING' AND
next_attempt_at = :seen`` that pushes ``next_attempt_at`` into the future (a
short lease) and is committed before any send. Only the dispatcher whose
UPDATE affected one row sends the message; the loser skips it. The lease also
means a dispatcher that crashes mid-send leaves a row that simply becomes due
again after ``CLAIM_LEASE_SECONDS``. The final transition (SENT / retry /
FAILED) is itself conditional on the claim still being ours. This is portable
(SQLite and PostgreSQL) and needs no extra enum value.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core import campus_rules, campus_time
from app.core.ws_manager import manager
from app.models.campus_model import OutboxMessage, OutboxStatus, PartyEvent

logger = logging.getLogger(__name__)

CLAIM_LEASE_SECONDS = 30
OUTBOX_SEND_TIMEOUT_SECONDS = 5  # a stalled socket must not block a dispatch pass
CLAIM_MARK = "claimed:"  # last_error prefix of a row leased by a live dispatcher
DEFAULT_FLUSH_LIMIT = 50


def _now(now: Optional[datetime]) -> datetime:
    return now if now is not None else campus_time.utcnow()


async def _dispatch_due(
    db: Session,
    now: datetime,
    limit: int,
    party_id: Optional[int] = None,
    user_id: Optional[int] = None,
    force: bool = False,
) -> int:
    """Claim and push due PENDING rows (optionally scoped). Returns the number SENT.

    ``force`` ignores the retry backoff (``next_attempt_at``) but never takes a
    row that another dispatcher currently holds under a live lease.
    """
    sent = 0
    try:
        now_db = campus_time.to_db(now)
        query = db.query(OutboxMessage.id, OutboxMessage.next_attempt_at).filter(
            OutboxMessage.status == OutboxStatus.PENDING
        )
        if force:
            query = query.filter(
                or_(
                    OutboxMessage.next_attempt_at <= now_db,
                    OutboxMessage.last_error.is_(None),
                    ~OutboxMessage.last_error.like(CLAIM_MARK + "%"),
                )
            )
        else:
            query = query.filter(OutboxMessage.next_attempt_at <= now_db)
        if party_id is not None:
            query = query.join(PartyEvent, PartyEvent.id == OutboxMessage.event_id).filter(
                PartyEvent.party_id == party_id
            )
        if user_id is not None:
            query = query.filter(OutboxMessage.recipient_id == user_id)
        due: List = query.order_by(OutboxMessage.id).limit(max(int(limit), 0)).all()
        db.rollback()  # end the read transaction; each row below commits on its own
    except Exception:
        logger.exception("Outbox: could not list due rows")
        _safe_rollback(db)
        return 0

    for row_id, seen_next in due:
        try:
            if await _deliver_one(db, row_id, seen_next, now_db):
                sent += 1
        except Exception:  # per-row isolation: one bad row never stops the rest
            logger.exception("Outbox: unexpected error on row %s", row_id)
            _safe_rollback(db)
    return sent


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception("Outbox: rollback failed")


async def _send_with_timeout(payload: dict, recipient_id: int):
    """``manager.send_personal_message`` bounded by OUTBOX_SEND_TIMEOUT_SECONDS.

    Raises asyncio.TimeoutError on a stalled socket. Deliberately not
    ``asyncio.wait_for``: on Python 3.11 it can swallow a cancellation that
    races with the inner coroutine finishing, which would make the poller
    impossible to cancel at shutdown.
    """
    send = asyncio.ensure_future(manager.send_personal_message(payload, recipient_id))
    try:
        done, _pending = await asyncio.wait({send}, timeout=OUTBOX_SEND_TIMEOUT_SECONDS)
    except BaseException:  # includes CancelledError: do not leak the send task
        send.cancel()
        raise
    if not done:
        send.cancel()
        raise asyncio.TimeoutError()
    return send.result()


async def _deliver_one(db: Session, row_id: int, seen_next: datetime, now_db: datetime) -> bool:
    lease_until = now_db + timedelta(seconds=CLAIM_LEASE_SECONDS)
    token = CLAIM_MARK + uuid.uuid4().hex

    # 1. Claim (atomic compare-and-set), committed BEFORE sending.
    claim = db.execute(
        update(OutboxMessage)
        .where(
            OutboxMessage.id == row_id,
            OutboxMessage.status == OutboxStatus.PENDING,
            OutboxMessage.next_attempt_at == seen_next,
        )
        .values(next_attempt_at=lease_until, last_error=token)
    )
    db.commit()
    if claim.rowcount != 1:
        return False  # another dispatcher got it

    row = db.query(OutboxMessage).filter(OutboxMessage.id == row_id).populate_existing().first()
    if row is None:
        return False
    recipient_id = row.recipient_id
    payload = dict(row.payload or {})
    attempts = row.attempts or 0
    db.rollback()

    # 2. Send (never trusted not to fail).
    error: Optional[str] = None
    delivered = 0
    try:
        delivered = int((await _send_with_timeout(payload, recipient_id)) or 0)
    except asyncio.TimeoutError:
        error = "send_timeout"
        logger.warning("Outbox: send timed out for row %s", row_id)
    except Exception as exc:
        error = f"send_error:{type(exc).__name__}"
        logger.warning("Outbox: send failed for row %s (%s)", row_id, type(exc).__name__)
    if delivered <= 0 and error is None:
        error = "no_live_socket"

    # 3. Record the outcome, only if the claim is still ours.
    where = (
        OutboxMessage.id == row_id,
        OutboxMessage.status == OutboxStatus.PENDING,
        OutboxMessage.last_error == token,
    )
    if delivered > 0:
        values = {"status": OutboxStatus.SENT, "sent_at": now_db, "last_error": None}
    else:
        attempts += 1
        if attempts >= campus_rules.OUTBOX_MAX_ATTEMPTS:
            values = {"status": OutboxStatus.FAILED, "attempts": attempts, "last_error": error}
        else:
            values = {
                "attempts": attempts,
                "last_error": error,
                "next_attempt_at": now_db + timedelta(seconds=campus_rules.backoff_seconds(attempts)),
            }
    db.execute(update(OutboxMessage).where(*where).values(**values))
    db.commit()
    return delivered > 0


async def dispatch_for_party(db: Session, party_id: int) -> int:
    """Try to push the party's due PENDING outbox rows. Returns the number sent. Never raises."""
    try:
        return await _dispatch_due(
            db, _now(None), limit=1000, party_id=party_id
        )
    except Exception:
        logger.exception("Outbox: dispatch_for_party failed")
        return 0


async def dispatch_for_user(
    db: Session,
    user_id: int,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_FLUSH_LIMIT,
    force: bool = True,
) -> int:
    """Flush one user's PENDING rows (called when their socket connects). Never raises.

    ``force`` (default) sends them regardless of retry backoff: the user is
    demonstrably online now. The claim/lease and attempt accounting still apply.
    """
    try:
        return await _dispatch_due(db, _now(now), limit=limit, user_id=user_id, force=force)
    except Exception:
        logger.exception("Outbox: dispatch_for_user failed")
        return 0


async def flush_on_connect(db: Session, user_id: int) -> None:
    """Socket-connect accelerator for both ws routers; must never break the socket."""
    try:
        await dispatch_for_user(db, user_id)
    except Exception:
        logger.exception("Outbox flush failed for user %s", user_id)


async def dispatch_pending(db: Session, now: Optional[datetime] = None, limit: int = 100) -> int:
    """Push every due PENDING outbox row (up to ``limit``). Returns the number sent. Never raises."""
    try:
        return await _dispatch_due(db, _now(now), limit=limit)
    except Exception:
        logger.exception("Outbox: dispatch_pending failed")
        return 0


def ack_up_to(db: Session, user_id: int, party_id: int, version: int) -> int:
    """Mark the user's outbox rows for events with version <= ``version`` as ACKED.

    Only PENDING and SENT rows change. Commits (so a client that has fetched
    /events is never re-pushed those events). Returns the number of rows acked.
    """
    event_ids = (
        db.query(PartyEvent.id)
        .filter(PartyEvent.party_id == party_id, PartyEvent.version <= version)
        .scalar_subquery()
    )
    result = db.execute(
        update(OutboxMessage)
        .where(
            OutboxMessage.recipient_id == user_id,
            OutboxMessage.status.in_([OutboxStatus.PENDING, OutboxStatus.SENT]),
            OutboxMessage.event_id.in_(event_ids),
        )
        .values(status=OutboxStatus.ACKED)
    )
    db.commit()
    return result.rowcount or 0
