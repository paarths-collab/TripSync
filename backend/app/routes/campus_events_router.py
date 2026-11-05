# backend/app/routes/campus_events_router.py
"""Campus events router: GET /parties/active and GET /events (reconciliation).

The server is authoritative; sockets only accelerate. A client that restarted
(or missed a push) calls ``/parties/active`` and ``/events`` and converges on
the same version and state from those two reads alone.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core import campus_rules, campus_time
from app.db.database import get_db
from app.models import user_model
from app.models.campus_model import (
    ChangeState,
    PartyChangeProposal,
    PartyEvent,
    PartyMember,
    PartyState,
    TravelParty,
)
from app.schemas.campus_schema import (
    ActivePartyResponse,
    EventOut,
    EventsResponse,
    PartyOut,
)
from app.services import auth_service, campus_outbox

router = APIRouter()

_ENDED_STATES = (PartyState.COMPLETED, PartyState.CANCELLED, PartyState.DISPUTED)


def _server_time() -> str:
    return campus_time.utc_iso(campus_time.utcnow())


def _member_parties(db: Session, user_id: int):
    """Parties the user is (or was) a member of."""
    return (
        db.query(TravelParty)
        .join(PartyMember, PartyMember.party_id == TravelParty.id)
        .filter(PartyMember.user_id == user_id)
    )


def _active_party(db: Session, user_id: int) -> Optional[TravelParty]:
    return (
        _member_parties(db, user_id)
        .filter(PartyMember.active.is_(True), TravelParty.state == PartyState.AGREED)
        .order_by(TravelParty.id.desc())
        .first()
    )


def _recently_ended_party(db: Session, user_id: int) -> Optional[TravelParty]:
    cutoff = campus_time.to_db(
        campus_time.utcnow() - timedelta(hours=campus_rules.RECENT_ENDED_HOURS)
    )
    return (
        _member_parties(db, user_id)
        .filter(
            TravelParty.state.in_(_ENDED_STATES),
            TravelParty.ended_at.isnot(None),
            TravelParty.ended_at >= cutoff,
        )
        .order_by(TravelParty.ended_at.desc(), TravelParty.id.desc())
        .first()
    )


def _party_view(db: Session, party: TravelParty, viewer_id: int) -> PartyOut:
    pending = (
        db.query(PartyChangeProposal)
        .filter(
            PartyChangeProposal.party_id == party.id,
            PartyChangeProposal.state == ChangeState.PENDING,
        )
        .order_by(PartyChangeProposal.id.desc())
        .first()
    )
    return PartyOut.from_party(party, viewer_id, pending_change=pending)


@router.get("/parties/active", response_model=ActivePartyResponse)
async def get_active_party(
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """The caller's AGREED party and their most recent recently-ended party."""
    user_id = current_user.id
    active = _active_party(db, user_id)
    ended = _recently_ended_party(db, user_id)
    party_view = _party_view(db, active, user_id) if active is not None else None
    ended_view = _party_view(db, ended, user_id) if ended is not None else None
    reference = active if active is not None else ended
    return ActivePartyResponse(
        party=party_view,
        recently_ended=ended_view,
        latest_version=reference.version if reference is not None else None,
        server_time=_server_time(),
    )


@router.get("/events", response_model=EventsResponse)
async def get_events(
    after_version: int = Query(0, ge=0),
    party_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """Party events newer than ``after_version`` plus the party's current view.

    ``party_id`` defaults to the caller's AGREED party, else their most recent
    party. Members only (404 otherwise). Also acknowledges the caller's outbox
    rows up to the latest version, so an acknowledged event is never re-pushed.
    """
    user_id = current_user.id
    if party_id is not None:
        party = _member_parties(db, user_id).filter(TravelParty.id == party_id).first()
        if party is None:
            raise HTTPException(status_code=404, detail="Party not found")
    else:
        party = _active_party(db, user_id)
        if party is None:
            party = _member_parties(db, user_id).order_by(TravelParty.id.desc()).first()
        if party is None:
            return EventsResponse(
                party_id=None, events=[], latest_version=None, party=None,
                server_time=_server_time(),
            )

    events = (
        db.query(PartyEvent)
        .filter(PartyEvent.party_id == party.id, PartyEvent.version > after_version)
        .order_by(PartyEvent.version.asc())
        .all()
    )
    latest_version = party.version
    if events:
        latest_version = max(latest_version, events[-1].version)

    response = EventsResponse(
        party_id=party.id,
        events=[EventOut.from_event(e) for e in events],
        latest_version=latest_version,
        party=_party_view(db, party, user_id),
        server_time=_server_time(),
    )
    # Ack after the response model is built (commit expires ORM state).
    campus_outbox.ack_up_to(db, user_id, response.party_id, latest_version)
    return response
