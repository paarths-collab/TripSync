# backend/app/services/connection_access.py
"""Single source of truth for "may these two users talk to each other?".

An *active ride connection* between users A and B is a PoolingConnection that
is APPROVED, whose sender/receiver requests belong to A and B (in either
direction), and whose two requests are both CONNECTED. Once a ride is
cancelled/completed the requests leave CONNECTED, so the pair is no longer
considered active (the connection row may stay APPROVED as history).
"""

from typing import Any, Optional, Set

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, aliased

from app.models.pooling_model import (
    PoolingConnection,
    PoolingConnectionStatus,
    PoolingRequest,
    PoolingRequestStatus,
)


def get_active_ride_connection(
    db: Session, user_a_id: int, user_b_id: int
) -> Optional[PoolingConnection]:
    """Return the active ride connection between two users, or None."""
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


def users_have_active_ride(db: Session, user_a_id: int, user_b_id: int) -> bool:
    return get_active_ride_connection(db, user_a_id, user_b_id) is not None


def get_active_partner_ids(db: Session, user_id: int) -> Set[int]:
    """All user ids that currently share an active ride connection with user_id."""
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
    db: Session, sender_id: int, receiver_id: Any, connection_id: Any = None
) -> Optional[PoolingConnection]:
    """Authorize a socket chat relay from sender_id to a client-supplied receiver.

    Returns the active PoolingConnection if the relay is allowed, else None.
    The receiver must be a valid id different from the sender, an active ride
    must exist between the two, and, if the client names a connection_id, it
    must be that connection's id.
    """
    receiver = _as_int_id(receiver_id)
    if receiver is None or receiver == sender_id:
        return None

    connection = get_active_ride_connection(db, sender_id, receiver)
    if connection is None:
        return None

    if connection_id is not None:
        claimed = _as_int_id(connection_id)
        if claimed is None or claimed != connection.id:
            return None

    return connection
