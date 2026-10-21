# backend/app/services/campus_outbox.py
"""Outbox dispatch for party events (stub: the real dispatcher replaces this module).

Callers commit state + event + outbox rows in one transaction and then call
``dispatch_for_party`` best-effort. It must never raise and never change party state.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session


async def dispatch_for_party(db: Session, party_id: int) -> int:
    """Try to push the party's PENDING outbox rows. Returns the number sent."""
    return 0


async def dispatch_pending(db: Session, now: Optional[datetime] = None, limit: int = 100) -> int:
    """Push every due PENDING outbox row. Returns the number sent."""
    return 0


def ack_up_to(db: Session, user_id: int, party_id: int, version: int) -> int:
    """Mark the user's outbox rows for events with version <= ``version`` as ACKED."""
    return 0
