# backend/app/services/connection_access.py
"""Single source of truth for "may these two users talk to each other?".

An *active ride connection* between users A and B is a PoolingConnection that
is APPROVED, whose sender/receiver requests belong to A and B (in either
direction), and whose two requests are both CONNECTED. Once a ride is
cancelled/completed the requests leave CONNECTED, so the pair is no longer
considered active (the connection row may stay APPROVED as history).

Campus scheduling adds a second, independent source of the same permission:
two users are also active partners while both are ACTIVE PartyMembers of one
TravelParty whose state is AGREED. Chat and contact access therefore derive
from party membership; once the party is CANCELLED / COMPLETED / DISPUTED
(members become inactive) the permission is gone. Either source suffices.
"""

from typing import Any, Optional, Set, Union

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, aliased

from app.models.campus_model import PartyMember, PartyState, TravelParty
from app.models.pooling_model import (
    PoolingConnection,
    PoolingConnectionStatus,
    PoolingRequest,
    PoolingRequestStatus,
)


def get_active_pooling_connection(
    db: Session, user_a_id: int, user_b_id: int
) -> Optional[PoolingConnection]:
    """Return the active LEGACY pooling connection between two users, or None."""
    if user_a_id is None or user_b_id is None or user_a_id == user_b_id:
        return None

    sender_req = aliased(PoolingRequest)
    receiver_req = aliased(PoolingRequest)

    return (
        db.query(PoolingConnection)
        .join(sender_req, PoolingConnection.sender_request_id == sender_req.id)
        .join(receiver_req, PoolingConnection.receiver_request_id == receiver_req.id)
        .filter(
            PoolingConnection.status == PoolingConnectionStatus.APPROVED,
            sender_req.status == PoolingRequestStatus.CONNECTED,
            receiver_req.status == PoolingRequestStatus.CONNECTED,
            or_(
                and_(sender_req.user_id == user_a_id, receiver_req.user_id == user_b_id),
                and_(sender_req.user_id == user_b_id, receiver_req.user_id == user_a_id),
            ),
        )
        .order_by(PoolingConnection.id.desc())
        .first()
    )


def get_active_party(db: Session, user_a_id: int, user_b_id: int) -> Optional[TravelParty]:
    """The AGREED TravelParty in which both users are ACTIVE members, or None."""
    if user_a_id is None or user_b_id is None or user_a_id == user_b_id:
        return None

    member_a = aliased(PartyMember)
    member_b = aliased(PartyMember)
    return (
        db.query(TravelParty)
        .join(member_a, member_a.party_id == TravelParty.id)
        .join(member_b, member_b.party_id == TravelParty.id)
        .filter(
            TravelParty.state == PartyState.AGREED,
            member_a.user_id == user_a_id,
            member_a.active.is_(True),
            member_b.user_id == user_b_id,
            member_b.active.is_(True),
        )
        .order_by(TravelParty.id.desc())
        .first()
    )


def get_active_ride_connection(
    db: Session, user_a_id: int, user_b_id: int
) -> Optional[Union[PoolingConnection, TravelParty]]:
    """The active grant between two users: a legacy PoolingConnection, else an
    AGREED TravelParty, else None."""
    connection = get_active_pooling_connection(db, user_a_id, user_b_id)
    if connection is not None:
        return connection
    return get_active_party(db, user_a_id, user_b_id)


def users_have_active_ride(db: Session, user_a_id: int, user_b_id: int) -> bool:
    return get_active_ride_connection(db, user_a_id, user_b_id) is not None


def _get_active_party_partner_ids(db: Session, user_id: int) -> Set[int]:
    mine = aliased(PartyMember)
    theirs = aliased(PartyMember)
    rows = (
        db.query(theirs.user_id)
        .select_from(TravelParty)
        .join(mine, mine.party_id == TravelParty.id)
        .join(theirs, theirs.party_id == TravelParty.id)
        .filter(
            TravelParty.state == PartyState.AGREED,
            mine.user_id == user_id,
            mine.active.is_(True),
            theirs.active.is_(True),
            theirs.user_id != user_id,
        )
        .all()
    )
    return {row[0] for row in rows}


def get_active_partner_ids(db: Session, user_id: int) -> Set[int]:
    """All user ids that currently share an active ride connection or an AGREED
    party with user_id."""
    return _get_active_pooling_partner_ids(db, user_id) | _get_active_party_partner_ids(
        db, user_id
    )


def _get_active_pooling_partner_ids(db: Session, user_id: int) -> Set[int]:
    sender_req = aliased(PoolingRequest)
    receiver_req = aliased(PoolingRequest)

    rows = (
        db.query(sender_req.user_id, receiver_req.user_id)
        .select_from(PoolingConnection)
        .join(sender_req, PoolingConnection.sender_request_id == sender_req.id)
        .join(receiver_req, PoolingConnection.receiver_request_id == receiver_req.id)
        .filter(
            PoolingConnection.status == PoolingConnectionStatus.APPROVED,
            sender_req.status == PoolingRequestStatus.CONNECTED,
            receiver_req.status == PoolingRequestStatus.CONNECTED,
            or_(sender_req.user_id == user_id, receiver_req.user_id == user_id),
        )
        .all()
    )
    partners: Set[int] = set()
    for sender_user_id, receiver_user_id in rows:
        other = receiver_user_id if sender_user_id == user_id else sender_user_id
        if other != user_id:
            partners.add(other)
    return partners


def grant_ref(grant: Union[PoolingConnection, TravelParty]) -> dict:
    """Payload reference for an authorized relay: connection_id (legacy) or party_id."""
    if isinstance(grant, TravelParty):
        return {"party_id": grant.id}
    return {"connection_id": grant.id}


def _as_int_id(value: Any) -> Optional[int]:
    """Accept real ints (not bools) and plain digit strings; anything else is None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def authorize_relay(
    db: Session,
    sender_id: int,
    receiver_id: Any,
    connection_id: Any = None,
    party_id: Any = None,
) -> Optional[Union[PoolingConnection, TravelParty]]:
    """Authorize a socket chat relay from sender_id to a client-supplied receiver.

    Returns the active PoolingConnection (legacy) or the AGREED TravelParty if
    the relay is allowed, else None. The receiver must be a valid id different
    from the sender and an active ride or party must exist between the two.
    A client-supplied connection_id / party_id must be the authorized
    connection's / party's id; naming one that does not exist or does not
    match refuses the relay (even if the other kind of grant would allow it).
    """
    receiver = _as_int_id(receiver_id)
    if receiver is None or receiver == sender_id:
        return None

    connection = get_active_pooling_connection(db, sender_id, receiver)
    party = get_active_party(db, sender_id, receiver)
    if connection is None and party is None:
        return None

    if connection_id is not None:
        claimed = _as_int_id(connection_id)
        if connection is None or claimed is None or claimed != connection.id:
            return None

    if party_id is not None:
        claimed = _as_int_id(party_id)
        if party is None or claimed is None or claimed != party.id:
            return None

    # Both grants can exist at once. The one the client named wins; with no
    # hint the legacy connection (the older, byte-compatible grant) is used.
    if connection is not None and (connection_id is not None or party_id is None):
        return connection
    return party if party is not None else connection
