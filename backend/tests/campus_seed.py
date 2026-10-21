"""Direct-DB seeding helpers for the campus events / outbox / chat-access tests.

Parties are built straight from the models plus ``campus_events.record_party_event``
(never through the party endpoints) so these tests do not depend on the code
that creates parties in production. Fictional data only.
"""

from datetime import timedelta

from app.core import campus_time
from app.models.campus_model import (
    Direction,
    PartyEventType,
    PartyMember,
    PartyState,
    TravelParty,
    TravelRequest,
    TravelRequestStatus,
)
from app.models.pooling_model import (
    PoolingConnection,
    PoolingConnectionStatus,
    PoolingRequest,
    PoolingRequestStatus,
)
from app.services import campus_events


def seed_party(
    factory, clock, landmarks, make_travel_request, user_a, user_b, *, departure_offset_min=60
):
    """AGREED party for two users: 2 RESERVED requests, 2 active members, PARTY_AGREED (v1).

    Returns the party id.
    """
    req_a = make_travel_request(
        user_a, landmarks, start_offset_min=30, end_offset_min=120, status="RESERVED"
    )
    req_b = make_travel_request(
        user_b, landmarks, start_offset_min=30, end_offset_min=120, status="RESERVED"
    )
    db = factory()
    try:
        now = clock.now
        party = TravelParty(
            state=PartyState.AGREED,
            agreed_departure=campus_time.to_db(now + timedelta(minutes=departure_offset_min)),
            meeting_landmark_id=landmarks["campus"].id,
            hub_id=landmarks["hub"].id,
            direction=Direction.TO_HUB,
            timezone="Asia/Kolkata",
            transport_responsibility="Participants arrange and pay for the taxi themselves.",
            version=0,
            created_at=campus_time.to_db(now),
        )
        db.add(party)
        db.flush()
        for user, req in ((user_a, req_a), (user_b, req_b)):
            db.add(PartyMember(party_id=party.id, user_id=user.id, request_id=req.id, active=True))
        db.flush()
        campus_events.record_party_event(
            db, party, user_a.id, PartyEventType.PARTY_AGREED, {"seed": True}, now
        )
        db.commit()
        return party.id
    finally:
        db.close()


def end_party(factory, clock, party_id, actor_id, *, state=PartyState.CANCELLED,
              event_type=PartyEventType.PARTY_CANCELLED, reason="seed_cancel"):
    """Directly end a party: state, ended_at, members inactive, requests ended, event + outbox."""
    db = factory()
    try:
        party = db.get(TravelParty, party_id)
        now = clock.now
        party.state = state
        party.ended_at = campus_time.to_db(now)
        party.end_reason = reason
        members = db.query(PartyMember).filter(PartyMember.party_id == party_id).all()
        for member in members:
            member.active = False
            req = db.get(TravelRequest, member.request_id)
            req.status = TravelRequestStatus.CANCELLED
        campus_events.record_party_event(db, party, actor_id, event_type, {"reason": reason}, now)
        db.commit()
    finally:
        db.close()


def add_event(factory, clock, party_id, actor_id, event_type=PartyEventType.NOTE_UPDATED,
              payload=None, **party_fields):
    """Record one more event (optionally updating party columns) and commit."""
    db = factory()
    try:
        party = db.get(TravelParty, party_id)
        for key, value in party_fields.items():
            setattr(party, key, value)
        campus_events.record_party_event(db, party, actor_id, event_type, payload or {}, clock.now)
        db.commit()
    finally:
        db.close()


def seed_legacy_pair(factory, user_a, user_b,
                     req_status=PoolingRequestStatus.CONNECTED,
                     conn_status=PoolingConnectionStatus.APPROVED):
    """Legacy pooling connection (a sends to b). Returns (connection_id, [request ids])."""
    db = factory()
    try:
        reqs = []
        for user in (user_a, user_b):
            req = PoolingRequest(
                user_id=user.id, status=req_status,
                start_latitude=19.0, start_longitude=72.8,
                destination_latitude=19.1, destination_longitude=72.9,
            )
            db.add(req)
            reqs.append(req)
        db.flush()
        conn = PoolingConnection(
            sender_request_id=reqs[0].id, receiver_request_id=reqs[1].id, status=conn_status
        )
        db.add(conn)
        db.commit()
        return conn.id, [r.id for r in reqs]
    finally:
        db.close()
