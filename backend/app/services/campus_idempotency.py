# backend/app/services/campus_idempotency.py
"""Idempotency records for retried campus mutations (accept / cancel).

Protocol used by the services:
1. ``find_replay`` before doing any work, and AGAIN after the row locks are held
   (a concurrent request with the same key may have committed in between).
2. On the success path, ``store`` the 2xx response in the SAME transaction as the
   state change, then commit once.
3. A unique-constraint race on (user_id, operation, key) surfaces as
   ``IntegrityError`` from ``store`` (flush). The caller rolls back, calls
   ``find_replay`` again and returns the stored body: the retry path.

Only 2xx responses are stored. A key reused for a different target is a client
bug -> 422 ``idempotency_key_reused``.
"""

import copy
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import campus_time
from app.models.campus_model import IdempotencyRecord

OP_ACCEPT_CONNECTION = "accept_connection"
OP_CANCEL_PARTY = "cancel_party"

REPLAY_HEADER = "Idempotent-Replay"


def sanitize_body(body: Any) -> Any:
    """Copy of ``body`` with the partner's phone/email nulled (privacy at rest).

    Works for a party view and for ``{"connection": ..., "party": ...}``. Replays
    rebuild the view from current state, so nothing depends on stored contacts.
    """
    out = copy.deepcopy(body)
    party = out.get("party") if isinstance(out, dict) and isinstance(out.get("party"), dict) else out
    if isinstance(party, dict) and isinstance(party.get("partner"), dict):
        party["partner"]["phone_number"] = None
        party["partner"]["email"] = None
    return out


def find_replay(
    db: Session, user_id: int, operation: str, key: str, target_id: int
) -> Optional[Any]:
    """Stored response body for (user, operation, key), or None.

    Raises 422 ``idempotency_key_reused`` when the key was already used by this
    user for this operation on a different target.
    """
    record = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
        .populate_existing()
        .first()
    )
    if record is None:
        return None
    if record.target_id != target_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "idempotency_key_reused",
                "message": "This idempotency key was already used for a different request.",
            },
        )
    return record.response_body


def store(
    db: Session,
    user_id: int,
    operation: str,
    key: str,
    target_id: int,
    status: int,
    body: Any,
) -> bool:
    """Stage an IdempotencyRecord on the caller's transaction (flushes, never commits).

    Non-2xx responses are not stored (returns False). A duplicate (user,
    operation, key) raises ``sqlalchemy.exc.IntegrityError`` for the caller's
    rollback-and-replay path.
    """
    if not 200 <= status < 300:
        return False
    db.add(
        IdempotencyRecord(
            user_id=user_id,
            operation=operation,
            key=key,
            target_id=target_id,
            response_status=status,
            response_body=sanitize_body(body),
            created_at=campus_time.to_db(campus_time.utcnow()),
        )
    )
    db.flush()
    return True
