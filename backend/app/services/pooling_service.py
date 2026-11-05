# backend/app/services/pooling_service.py
"""Pooling business logic.

Contract shared with chat authorization: an *active ride* is a PoolingConnection
that is APPROVED and whose two requests are both CONNECTED. Ending a ride via
cancel sets BOTH requests to CANCELLED and leaves the connection APPROVED
(history). A request never goes from CANCELLED back to CONNECTED.

All WebSocket notifications are sent only AFTER the database commit succeeded,
through ``_notify`` which never raises.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.core.config import settings
from app.core.ws_manager import manager
from app.models import pooling_model, user_model
from app.schemas import pooling_schema

logger = logging.getLogger(__name__)

# --- Constants for matching logic ---
START_LOCATION_RADIUS_METERS = 5000  # 5km (inclusive)
DESTINATION_RADIUS_METERS = 5000  # 5km (inclusive)
ACTIVE_TIMEOUT_MINUTES = 15
MAX_PENDING_CONNECTIONS = 5
OLA_DISTANCE_MATRIX_BASIC_API_URL = "https://api.olamaps.io/routing/v1/distanceMatrix/basic"

_RequestStatus = pooling_model.PoolingRequestStatus
_ConnStatus = pooling_model.PoolingConnectionStatus
_OPEN_STATUSES = (_RequestStatus.ACTIVE, _RequestStatus.MATCHED)

Notification = Tuple[int, dict]


class MatchingProviderError(Exception):
    """The distance-matrix provider failed or returned an unusable answer."""


class MatchingProviderTimeout(MatchingProviderError):
    """The distance-matrix provider timed out."""


async def _notify(user_id: int, message: dict) -> None:
    """Best-effort WebSocket push. Never raises (a socket failure must not undo
    or fail an already-committed action)."""
    try:
        await manager.send_personal_message(message, user_id)
    except Exception as exc:  # noqa: BLE001 - deliberately broad
        logger.warning(
            "WebSocket notification failed (type=%s user_id=%s): %s",
            message.get("type") if isinstance(message, dict) else None,
            user_id,
            type(exc).__name__,
        )


async def _notify_all(notifications: List[Notification]) -> None:
    for user_id, message in notifications:
        await _notify(user_id, message)


# ==================== DISTANCE MATRIX PROVIDER ====================

async def _get_distances_from_ola(origin: tuple, destinations: List[tuple]) -> List[float | None]:
    """
    Call the OLA Distance Matrix Basic API: one distance (metres) per destination.

    A destination the provider reports as not OK yields None (a legitimate
    non-match). Any provider-level failure (timeout, transport error, HTTP error,
    carrier block page, invalid JSON, non-SUCCESS status, malformed or
    wrong-sized matrix) raises MatchingProviderError / MatchingProviderTimeout.
    Never logs the URL, query params (they hold the API key) or response bodies.
    """
    if not destinations:
        return []

    params = {
        "origins": f"{origin[0]},{origin[1]}",
        "destinations": "|".join(f"{dest[0]},{dest[1]}" for dest in destinations),
        "api_key": settings.OLA_MAPS_API_KEY,
    }

    client_config = {
        "timeout": 20.0,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://olamaps.io/",
        },
    }
    proxy_config = getattr(settings, "OLA_MAPS_PROXY", None)
    if proxy_config:
        client_config["proxy"] = proxy_config  # httpx >= 0.26 (``proxies`` was removed)

    try:
        async with httpx.AsyncClient(**client_config) as client:
            response = await client.get(OLA_DISTANCE_MATRIX_BASIC_API_URL, params=params)
    except httpx.TimeoutException as exc:
        logger.warning("Distance matrix provider timed out (%s)", type(exc).__name__)
        raise MatchingProviderTimeout("Distance matrix provider timed out") from None
    except Exception as exc:  # noqa: BLE001 - transport errors; message may embed the URL
        logger.warning("Distance matrix provider request failed (%s)", type(exc).__name__)
        raise MatchingProviderError("Distance matrix provider request failed") from None

    if not 200 <= response.status_code < 300:
        logger.warning("Distance matrix provider returned HTTP %s", response.status_code)
        raise MatchingProviderError("Distance matrix provider returned an error status")

    try:
        payload = response.json()
    except ValueError:
        # Includes carrier "Web Filter Violation" / "Access Blocked" HTML pages.
        logger.warning("Distance matrix provider returned a non-JSON body (HTTP %s)", response.status_code)
        raise MatchingProviderError("Distance matrix provider returned an invalid response") from None

    if not isinstance(payload, dict) or payload.get("status") != "SUCCESS":
        logger.warning("Distance matrix provider reported a non-SUCCESS status")
        raise MatchingProviderError("Distance matrix provider reported a failure")

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        logger.warning("Distance matrix provider returned no rows")
        raise MatchingProviderError("Distance matrix provider returned a malformed matrix")
    elements = rows[0].get("elements")
    if not isinstance(elements, list) or len(elements) != len(destinations):
        logger.warning(
            "Distance matrix element count mismatch (expected %s)", len(destinations)
        )
        raise MatchingProviderError("Distance matrix provider returned a malformed matrix")

    distances: List[float | None] = []
    for element in elements:
        distance = None
        if isinstance(element, dict) and element.get("status") == "OK":
            raw = element.get("distance")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                distance = float(raw)
        distances.append(distance)
    return distances


# ==================== LOCKING ====================
# Lock-ordering rule used everywhere (prevents Postgres deadlocks; harmless on
# SQLite): lock every involved PoolingRequest row with SELECT ... FOR UPDATE in
# ASCENDING id order FIRST, and only then touch PoolingConnection rows. Rows are
# re-read (populate_existing) so statuses are the latest committed ones.

def _lock_requests(db: Session, request_ids) -> dict:
    ids = sorted({i for i in request_ids if i is not None})
    if not ids:
        return {}
    rows = db.query(pooling_model.PoolingRequest).filter(
        pooling_model.PoolingRequest.id.in_(ids)
    ).order_by(pooling_model.PoolingRequest.id).populate_existing().with_for_update().all()
    return {r.id: r for r in rows}


# ==================== REQUEST LIFECYCLE ====================

def _reject_pending_for_requests(
    db: Session, request_ids: List[int], by_user: user_model.User, reason: str
) -> List[Notification]:
    """Mark PENDING connections touching any of request_ids as REJECTED (no commit).
    Returns notifications for the counterpart users (those not owning the ids)."""
    if not request_ids:
        return []
    pending = db.query(pooling_model.PoolingConnection).options(
        joinedload(pooling_model.PoolingConnection.sender_request),
        joinedload(pooling_model.PoolingConnection.receiver_request),
    ).filter(
        pooling_model.PoolingConnection.status == _ConnStatus.PENDING,
        or_(
            pooling_model.PoolingConnection.sender_request_id.in_(request_ids),
            pooling_model.PoolingConnection.receiver_request_id.in_(request_ids),
        ),
    ).order_by(pooling_model.PoolingConnection.id).all()
    notifications: List[Notification] = []
    now = datetime.utcnow()
    for conn in pending:
        conn.status = _ConnStatus.REJECTED
        conn.responded_at = now
        if conn.sender_request_id in request_ids and conn.receiver_request_id in request_ids:
            continue  # both ends are ours; nobody else to tell
        counterpart = conn.receiver_request if conn.sender_request_id in request_ids else conn.sender_request
        if counterpart.user_id == by_user.id:
            continue
        notifications.append((counterpart.user_id, {
            "type": "connection_rejected",
            "connection_id": conn.id,
            "by_user": {"id": by_user.id, "full_name": by_user.full_name},
            "reason": reason,
        }))
    return notifications


async def create_or_update_pooling_request(
    db: Session, user: user_model.User, request_data: pooling_schema.PoolingRequestCreate
) -> pooling_model.PoolingRequest:
    """
    Creates a new pooling request. Refuses (409) while the user has a CONNECTED
    ride. Otherwise cancels the user's previous ACTIVE and MATCHED requests,
    rejects every PENDING connection touching them and (after commit) tells the
    counterpart users.
    """
    user_id = user.id
    try:
        # Lock ALL of this user's live requests first, then decide: a concurrent
        # approval cannot leave the user CONNECTED plus a fresh ACTIVE request.
        live = db.query(pooling_model.PoolingRequest).filter(
            pooling_model.PoolingRequest.user_id == user_id,
            pooling_model.PoolingRequest.status.in_(
                (_RequestStatus.ACTIVE, _RequestStatus.MATCHED, _RequestStatus.CONNECTED)
            ),
        ).order_by(pooling_model.PoolingRequest.id).populate_existing().with_for_update().all()

        if any(r.status == _RequestStatus.CONNECTED for r in live):
            raise HTTPException(
                status_code=409,
                detail="You already have an active ride; end it before starting a new search",
            )

        stale = [r for r in live if r.status in _OPEN_STATUSES]
        stale_ids = [r.id for r in stale]

        notifications = _reject_pending_for_requests(db, stale_ids, user, "request_cancelled")
        for old in stale:
            old.status = _RequestStatus.CANCELLED

        new_request = pooling_model.PoolingRequest(
            user_id=user_id,
            start_latitude=request_data.start_latitude,
            start_longitude=request_data.start_longitude,
            destination_latitude=request_data.destination_latitude,
            destination_longitude=request_data.destination_longitude,
            destination_name=request_data.destination_name,
        )
        db.add(new_request)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(new_request)
    await _notify_all(notifications)
    return new_request


async def _abandon_search(db: Session, request_id: int, user_id: int, user_name: str) -> None:
    """Provider failed: cancel the just-created search request so other riders
    never see an un-searchable ghost. Best effort; never raises."""
    notifications: List[Notification] = []
    try:
        locked = _lock_requests(db, [request_id])
        req = locked.get(request_id)
        if req is not None and req.status in _OPEN_STATUSES:
            by = type("By", (), {"id": user_id, "full_name": user_name})()
            notifications = _reject_pending_for_requests(db, [request_id], by, "request_cancelled")
            req.status = _RequestStatus.CANCELLED
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not cancel request %s after provider failure (%s)", request_id, type(exc).__name__)
        return
    await _notify_all(notifications)


async def find_matches(db: Session, new_request: pooling_model.PoolingRequest) -> List[pooling_model.PoolingRequest]:
    """
    Finds compatible requests (ACTIVE or MATCHED, same non-null college, created
    within the last ACTIVE_TIMEOUT_MINUTES, other users), marks both sides MATCHED
    and, after committing, notifies the waiting users.

    The candidate list is read before the (slow) provider calls, so before writing
    anything the new request and the candidates are re-locked (ascending id) and
    re-read: a candidate that became CONNECTED/CANCELLED meanwhile is left alone and
    is neither returned nor notified; if the new request itself is no longer open
    nothing is written.

    Raises MatchingProviderError / MatchingProviderTimeout when the distance
    provider fails (never presented as "no matches"); the new search request is
    cancelled first.
    """
    time_threshold = datetime.utcnow() - timedelta(minutes=ACTIVE_TIMEOUT_MINUTES)
    searcher = new_request.user
    # Plain values: ORM objects expire on commit/rollback.
    new_request_id = new_request.id
    searcher_id, searcher_name, searcher_college = searcher.id, searcher.full_name, searcher.college_id

    if searcher_college is None:
        return []  # users without a college never match (None == None must not pair them)

    candidates = db.query(pooling_model.PoolingRequest).options(
        joinedload(pooling_model.PoolingRequest.user)
    ).filter(
        pooling_model.PoolingRequest.status.in_(_OPEN_STATUSES),
        pooling_model.PoolingRequest.id != new_request_id,
        pooling_model.PoolingRequest.user_id != new_request.user_id,
        pooling_model.PoolingRequest.user.has(and_(
            user_model.User.college_id.isnot(None),
            user_model.User.college_id == searcher_college,
        )),
        pooling_model.PoolingRequest.created_at >= time_threshold,
    ).order_by(pooling_model.PoolingRequest.id).all()

    logger.info("find_matches: request %s has %d candidate(s)", new_request_id, len(candidates))
    if not candidates:
        return []

    origin_start = (new_request.start_latitude, new_request.start_longitude)
    origin_dest = (new_request.destination_latitude, new_request.destination_longitude)
    try:
        # START proximity (inclusive radius)
        start_distances = await _get_distances_from_ola(
            origin_start, [(r.start_latitude, r.start_longitude) for r in candidates]
        )
        close_by_start = [
            req for req, distance in zip(candidates, start_distances)
            if distance is not None and distance <= START_LOCATION_RADIUS_METERS
        ]
        matched_ids: List[int] = []
        if close_by_start:
            # DESTINATION proximity (inclusive radius)
            dest_distances = await _get_distances_from_ola(
                origin_dest, [(r.destination_latitude, r.destination_longitude) for r in close_by_start]
            )
            matched_ids = [
                req.id for req, distance in zip(close_by_start, dest_distances)
                if distance is not None and distance <= DESTINATION_RADIUS_METERS
            ]
    except MatchingProviderError:
        await _abandon_search(db, new_request_id, searcher_id, searcher_name)
        raise

    if not matched_ids:
        return []

    notifications: List[Notification] = []
    try:
        locked = _lock_requests(db, [new_request_id] + matched_ids)
        me = locked.get(new_request_id)
        if me is None or me.status not in _OPEN_STATUSES:
            db.rollback()
            return []  # our own request was cancelled/connected while we searched
        still_open = [
            locked[i] for i in sorted(matched_ids)
            if i in locked and locked[i].status in _OPEN_STATUSES
        ]
        if not still_open:
            db.rollback()
            return []
        for matched in still_open:
            matched.status = _RequestStatus.MATCHED
            matched_user_data = pooling_schema.MatchedUser(
                id=searcher_id,
                full_name=searcher_name,
                phone_number=None,  # hidden until connected
                email=None,
                year_of_study=None,
                bio=None,
                profile_image_url=None,
                request_id=new_request_id,
                connection_status="none",
                connection_id=None,
            )
            notifications.append((matched.user_id, {
                "type": "match_found",
                "match": matched_user_data.model_dump(),
            }))
        me.status = _RequestStatus.MATCHED
        db.commit()
    except Exception:
        db.rollback()
        raise

    await _notify_all(notifications)
    return still_open


# ==================== CONNECTION MANAGEMENT ====================

async def send_connection_request(
    db: Session,
    sender_request_id: int,
    receiver_request_id: int,
    sender_user: user_model.User,
) -> pooling_model.PoolingConnection:
    """
    Sends a connection request from one pooling request to another.

    Eligibility (the "pair was actually matched" relationship is not persisted, so
    we enforce): both requests open (ACTIVE/MATCHED), different users, same
    college, no CONNECTED ride for the sender, no PENDING/APPROVED connection
    between the two requests in either direction.
    """
    try:
        # Lock both requests (ascending id) before the duplicate check so that
        # concurrent duplicate sends serialize (there is no unique constraint).
        locked = _lock_requests(db, [sender_request_id, receiver_request_id])
        sender_request = locked.get(sender_request_id)
        receiver_request = locked.get(receiver_request_id)

        if not sender_request or not receiver_request:
            raise HTTPException(status_code=404, detail="Request not found")

        if sender_request.user_id != sender_user.id:
            raise HTTPException(status_code=403, detail="Not your request")

        if receiver_request.user_id == sender_user.id:
            raise HTTPException(status_code=400, detail="You cannot connect to your own request")

        receiver_user = receiver_request.user
        if (
            receiver_user is None
            or receiver_user.college_id is None
            or sender_user.college_id is None
            or receiver_user.college_id != sender_user.college_id
        ):
            raise HTTPException(status_code=403, detail="Request belongs to a different college")

        sender_connected = db.query(pooling_model.PoolingRequest.id).filter(
            pooling_model.PoolingRequest.user_id == sender_user.id,
            pooling_model.PoolingRequest.status == _RequestStatus.CONNECTED,
        ).first()
        if sender_connected:
            raise HTTPException(status_code=409, detail="You already have an active ride")

        if sender_request.status not in _OPEN_STATUSES:
            raise HTTPException(status_code=400, detail="Request is not active or matched")

        if receiver_request.status not in _OPEN_STATUSES:
            raise HTTPException(status_code=409, detail="That request is no longer available")

        existing = db.query(pooling_model.PoolingConnection).filter(
            pooling_model.PoolingConnection.status.in_([_ConnStatus.PENDING, _ConnStatus.APPROVED]),
            or_(
                and_(
                    pooling_model.PoolingConnection.sender_request_id == sender_request_id,
                    pooling_model.PoolingConnection.receiver_request_id == receiver_request_id,
                ),
                and_(
                    pooling_model.PoolingConnection.sender_request_id == receiver_request_id,
                    pooling_model.PoolingConnection.receiver_request_id == sender_request_id,
                ),
            ),
        ).first()
        if existing:
            if existing.status == _ConnStatus.PENDING:
                raise HTTPException(status_code=400, detail="Connection request already exists")
            raise HTTPException(status_code=400, detail="Already connected")

        pending_count = db.query(func.count(pooling_model.PoolingConnection.id)).filter(
            pooling_model.PoolingConnection.sender_request_id == sender_request_id,
            pooling_model.PoolingConnection.status == _ConnStatus.PENDING,
        ).scalar()
        if pending_count >= MAX_PENDING_CONNECTIONS:
            raise HTTPException(status_code=400, detail=f"Maximum {MAX_PENDING_CONNECTIONS} pending connections reached")

        connection = pooling_model.PoolingConnection(
            sender_request_id=sender_request_id,
            receiver_request_id=receiver_request_id,
            status=_ConnStatus.PENDING,
        )
        sender_id, sender_name = sender_user.id, sender_user.full_name
        receiver_id, receiver_name = receiver_user.id, receiver_user.full_name
        db.add(connection)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(connection)

    await _notify(receiver_id, {
        "type": "connection_request_received",
        "connection_id": connection.id,
        "from_user": {
            "id": sender_id,
            "full_name": sender_name,
            "request_id": sender_request_id,
        },
    })
    await _notify(sender_id, {
        "type": "connection_request_sent",
        "connection_id": connection.id,
        "to_user": {
            "id": receiver_id,
            "full_name": receiver_name,
            "request_id": receiver_request_id,
        },
    })
    return connection


def _approved_message(own_request_id: int, connection_id: int, partner: user_model.User, partner_request_id: int) -> dict:
    profile = partner.profile
    return {
        "type": "connection_approved",
        "connection_id": connection_id,
        "user_request_id": own_request_id,
        "partner": {
            "id": partner.id,
            "full_name": partner.full_name,
            "phone_number": profile.phone_number if profile else None,
            "email": partner.email,
            "year_of_study": profile.year_of_study if profile else None,
            "bio": profile.bio if profile else None,
            "request_id": partner_request_id,
        },
    }


async def respond_to_connection(
    db: Session,
    connection_id: int,
    action: str,
    responder_user: user_model.User,
) -> pooling_model.PoolingConnection:
    """
    Approve or reject a connection request.

    Approve is atomic: a conditional UPDATE claims the PENDING connection (409 if
    someone else already resolved it), both requests are locked and must still be
    ACTIVE/MATCHED (409 otherwise), both become CONNECTED and every other PENDING
    connection touching either request is rejected. Notifications go out only
    after the commit.
    """
    connection = db.query(pooling_model.PoolingConnection).options(
        joinedload(pooling_model.PoolingConnection.sender_request).joinedload(pooling_model.PoolingRequest.user),
        joinedload(pooling_model.PoolingConnection.receiver_request).joinedload(pooling_model.PoolingRequest.user),
    ).filter(pooling_model.PoolingConnection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if connection.receiver_request.user_id != responder_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to respond")

    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")

    sender_request_id = connection.sender_request_id
    receiver_request_id = connection.receiver_request_id
    sender_user = connection.sender_request.user
    new_status = _ConnStatus.APPROVED if action == "approve" else _ConnStatus.REJECTED
    notifications: List[Notification] = []

    try:
        # Lock-ordering rule: requests (ascending id) first, then the connection rows.
        # With READ COMMITTED a losing concurrent approver then sees the connection
        # already REJECTED/APPROVED and gets a clean 409 instead of a deadlock.
        locked_requests = _lock_requests(db, [sender_request_id, receiver_request_id])

        claimed = db.query(pooling_model.PoolingConnection).filter(
            pooling_model.PoolingConnection.id == connection_id,
            pooling_model.PoolingConnection.status == _ConnStatus.PENDING,
        ).update(
            {"status": new_status, "responded_at": datetime.utcnow()},
            synchronize_session=False,
        )
        if claimed != 1:
            raise HTTPException(status_code=409, detail="Connection already responded to")

        if action == "approve":
            requests = list(locked_requests.values())
            if len(requests) != 2 or any(r.status not in _OPEN_STATUSES for r in requests):
                raise HTTPException(
                    status_code=409,
                    detail="One of the requests is no longer available",
                )
            for r in requests:
                r.status = _RequestStatus.CONNECTED

            own_ids = [sender_request_id, receiver_request_id]
            others = db.query(pooling_model.PoolingConnection).options(
                joinedload(pooling_model.PoolingConnection.sender_request),
                joinedload(pooling_model.PoolingConnection.receiver_request),
            ).filter(
                pooling_model.PoolingConnection.id != connection_id,
                pooling_model.PoolingConnection.status == _ConnStatus.PENDING,
                or_(
                    pooling_model.PoolingConnection.sender_request_id.in_(own_ids),
                    pooling_model.PoolingConnection.receiver_request_id.in_(own_ids),
                ),
            ).all()
            now = datetime.utcnow()
            for other in others:
                other.status = _ConnStatus.REJECTED
                other.responded_at = now
                s_in = other.sender_request_id in own_ids
                r_in = other.receiver_request_id in own_ids
                if s_in and r_in:
                    continue
                affected, counterpart = (
                    (other.sender_request, other.receiver_request) if s_in
                    else (other.receiver_request, other.sender_request)
                )
                affected_user = sender_user if affected.id == sender_request_id else responder_user
                notifications.append((counterpart.user_id, {
                    "type": "connection_rejected",
                    "connection_id": other.id,
                    "by_user": {"id": affected_user.id, "full_name": affected_user.full_name},
                    "reason": "partner_unavailable",
                }))

            notifications.append((sender_user.id, _approved_message(
                sender_request_id, connection_id, responder_user, receiver_request_id)))
            notifications.append((responder_user.id, _approved_message(
                receiver_request_id, connection_id, sender_user, sender_request_id)))
        else:
            notifications.append((sender_user.id, {
                "type": "connection_rejected",
                "connection_id": connection_id,
                "by_user": {"id": responder_user.id, "full_name": responder_user.full_name},
            }))

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(connection)
    await _notify_all(notifications)
    return connection


def get_active_connection(db: Session, user_id: int) -> Optional[pooling_model.PoolingConnection]:
    """
    The user's active ride: an APPROVED connection whose two requests are both
    CONNECTED, one of them owned by the user.
    """
    user_request = db.query(pooling_model.PoolingRequest).filter(
        pooling_model.PoolingRequest.user_id == user_id,
        pooling_model.PoolingRequest.status == _RequestStatus.CONNECTED,
    ).order_by(pooling_model.PoolingRequest.created_at.desc(), pooling_model.PoolingRequest.id.desc()).first()
    if not user_request:
        return None

    s = aliased(pooling_model.PoolingRequest)
    r = aliased(pooling_model.PoolingRequest)
    user_with_profile = joinedload(pooling_model.PoolingRequest.user).joinedload(user_model.User.profile)
    return db.query(pooling_model.PoolingConnection).join(
        s, pooling_model.PoolingConnection.sender_request_id == s.id
    ).join(
        r, pooling_model.PoolingConnection.receiver_request_id == r.id
    ).options(
        joinedload(pooling_model.PoolingConnection.sender_request).options(user_with_profile),
        joinedload(pooling_model.PoolingConnection.receiver_request).options(user_with_profile),
    ).filter(
        pooling_model.PoolingConnection.status == _ConnStatus.APPROVED,
        s.status == _RequestStatus.CONNECTED,
        r.status == _RequestStatus.CONNECTED,
        or_(
            pooling_model.PoolingConnection.sender_request_id == user_request.id,
            pooling_model.PoolingConnection.receiver_request_id == user_request.id,
        ),
    ).order_by(pooling_model.PoolingConnection.id.desc()).first()


def get_latest_request(db: Session, user_id: int) -> Optional[pooling_model.PoolingRequest]:
    return db.query(pooling_model.PoolingRequest).filter(
        pooling_model.PoolingRequest.user_id == user_id
    ).order_by(
        pooling_model.PoolingRequest.created_at.desc(), pooling_model.PoolingRequest.id.desc()
    ).first()


def request_has_approved_connection(db: Session, request_id: int) -> bool:
    return db.query(pooling_model.PoolingConnection.id).filter(
        pooling_model.PoolingConnection.status == _ConnStatus.APPROVED,
        or_(
            pooling_model.PoolingConnection.sender_request_id == request_id,
            pooling_model.PoolingConnection.receiver_request_id == request_id,
        ),
    ).first() is not None


def _approved_partner_request_ids(db: Session, request_id: int) -> List[int]:
    rows = db.query(
        pooling_model.PoolingConnection.sender_request_id,
        pooling_model.PoolingConnection.receiver_request_id,
    ).filter(
        pooling_model.PoolingConnection.status == _ConnStatus.APPROVED,
        or_(
            pooling_model.PoolingConnection.sender_request_id == request_id,
            pooling_model.PoolingConnection.receiver_request_id == request_id,
        ),
    ).all()
    return sorted({i for row in rows for i in row if i != request_id})


async def cancel_pooling_request(db: Session, request_id: int, user: user_model.User):
    """
    Ends a pooling request. Idempotent: an already CANCELLED/COMPLETED request
    answers 200. For a CONNECTED ride both requests become CANCELLED (the
    connection stays APPROVED as history). Notifications are sent after commit;
    any failure before commit rolls back and re-raises, leaving the DB unchanged.

    Locking: the partner request ids are discovered first, then the request and its
    partners are locked together in ascending id order and everything is re-checked
    (if the partner set changed meanwhile, roll back and retry).
    """
    user_id, user_name = user.id, user.full_name
    by_user = type("By", (), {"id": user_id, "full_name": user_name})()
    notifications: List[Notification] = []

    for attempt in range(4):
        try:
            owned = db.query(pooling_model.PoolingRequest.id).filter(
                pooling_model.PoolingRequest.id == request_id,
                pooling_model.PoolingRequest.user_id == user_id,
            ).first()
            if not owned:
                raise HTTPException(status_code=404, detail="Request not found")

            partner_ids = _approved_partner_request_ids(db, request_id)
            locked = _lock_requests(db, [request_id] + partner_ids)
            request = locked.get(request_id)
            if request is None or request.user_id != user_id:
                raise HTTPException(status_code=404, detail="Request not found")

            # Partners may have changed between discovery and the lock: retry.
            if not set(_approved_partner_request_ids(db, request_id)) <= set(locked):
                db.rollback()
                continue

            if request.status in (_RequestStatus.CANCELLED, _RequestStatus.COMPLETED):
                db.rollback()
                return {"message": "Request already ended"}

            affected_ids = [request.id]
            notifications = []
            if request.status == _RequestStatus.CONNECTED:
                connections = db.query(pooling_model.PoolingConnection).filter(
                    pooling_model.PoolingConnection.status == _ConnStatus.APPROVED,
                    or_(
                        pooling_model.PoolingConnection.sender_request_id == request_id,
                        pooling_model.PoolingConnection.receiver_request_id == request_id,
                    ),
                ).order_by(pooling_model.PoolingConnection.id).all()
                for conn in connections:
                    partner_id = (
                        conn.sender_request_id if conn.receiver_request_id == request_id
                        else conn.receiver_request_id
                    )
                    partner_request = locked[partner_id]
                    if partner_request.status != _RequestStatus.CONNECTED:
                        continue
                    partner_request.status = _RequestStatus.CANCELLED
                    affected_ids.append(partner_request.id)
                    notifications.append((partner_request.user_id, {
                        "type": "ride_cancelled",
                        "by_user": {"id": user_id, "full_name": user_name},
                        "message": f"{user_name} cancelled the ride",
                        "request_id": partner_request.id,
                        "connection_id": conn.id,
                    }))

            notifications.extend(
                _reject_pending_for_requests(db, affected_ids, by_user, "request_cancelled")
            )
            request.status = _RequestStatus.CANCELLED
            db.commit()
            break
        except Exception:
            db.rollback()
            raise
    else:
        raise HTTPException(status_code=409, detail="Request changed while cancelling; please retry")

    await _notify_all(notifications)
    return {"message": "Request cancelled successfully"}
