# backend/app/services/campus_events.py
"""Party event log + transactional outbox rows.

``record_party_event`` only stages rows on the caller's session. It never
commits and never sends anything: the caller commits the state change, the
event and the outbox rows in ONE transaction, then dispatches best-effort
(see app.services.campus_outbox).
"""

from datetime import datetime
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.core import campus_time
from app.models.campus_model import (
    OutboxMessage,
    OutboxStatus,
    PartyEvent,
    PartyEventType,
    PartyMember,
    TravelParty,
)


def record_party_event(
    db: Session,
    party: TravelParty,
    actor_id: Optional[int],
    event_type: Union[PartyEventType, str],
    payload: Optional[dict],
    now: datetime,
) -> PartyEvent:
    """Bump ``party.version``, add the PartyEvent and one OutboxMessage per member.

    Members are every PartyMember row of the party, active or former, including
    the actor. ``now`` must be an aware datetime. Nothing is committed.
    """
    event_type = PartyEventType(event_type)  # ValueError on unknown types
    now_db = campus_time.to_db(now)

    # The session is autoflush=False: flush so a freshly built party (and its
    # members) are visible to the query below. A flush is not a commit.
    db.flush()
    members = (
        db.query(PartyMember)
        .filter(PartyMember.party_id == party.id)
        .order_by(PartyMember.id)
        .all()
    )

    party.version = (party.version or 0) + 1
    event = PartyEvent(
        party_id=party.id,
        version=party.version,
        actor_id=actor_id,
        event_type=event_type.value,
        payload=dict(payload or {}),
        occurred_at=now_db,
    )
    db.add(event)
    db.flush()  # assigns event.id for the outbox FK

    seen = set()
    for member in members:
        if member.user_id in seen:
            continue
        seen.add(member.user_id)
        db.add(
            OutboxMessage(
                event_id=event.id,
                recipient_id=member.user_id,
                payload={
                    "type": "party_event",
                    "party_id": party.id,
                    "version": party.version,
                    "event_type": event_type.value,
                },
                status=OutboxStatus.PENDING,
                attempts=0,
                next_attempt_at=now_db,
                created_at=now_db,
            )
        )
    db.flush()
    return event
