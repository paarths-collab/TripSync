# backend/app/services/campus_estimates.py
"""Corridor travel-time estimates for campus suggestions.

``corridor_estimate`` is an adapter around the routing provider
(``map_service.get_route_from_ola``) that uses the ``CorridorEstimate`` table
as a cache:

- a VERIFIED row is reused for ``ESTIMATE_TTL_MINUTES``;
- an UNVERIFIED row is not retried before ``ESTIMATE_RETRY_SECONDS`` have passed.

The adapter NEVER raises. A provider problem becomes an UNVERIFIED estimate
with a stable failure code so callers can still return suggestions:

    genuine "no route" (provider returns None)  -> "no_route"
    RoutingProviderTimeout / our own timeout    -> "timeout"
    any other provider or unexpected error      -> "unavailable"

Nothing here logs URLs, keys or coordinates above DEBUG.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import campus_time
from app.core.campus_rules import ESTIMATE_RETRY_SECONDS, ESTIMATE_TTL_MINUTES
from app.models.campus_model import CorridorEstimate, Direction, EstimateStatus
from app.services import map_service

logger = logging.getLogger(__name__)

# Hard ceiling for one provider call so an outage cannot stall a request for the
# provider client's own (longer) timeout.
PROVIDER_CALL_TIMEOUT_SECONDS = 8.0

FAILURE_NO_ROUTE = "no_route"
FAILURE_TIMEOUT = "timeout"
FAILURE_UNAVAILABLE = "unavailable"


def _val(x):
    return getattr(x, "value", x)


def _is_fresh(row: CorridorEstimate, now: datetime) -> bool:
    checked = campus_time.from_db(row.checked_at)
    status = _val(row.status)
    if status == EstimateStatus.VERIFIED.value and row.duration_s is not None:
        return checked > now - timedelta(minutes=ESTIMATE_TTL_MINUTES)
    return checked > now - timedelta(seconds=ESTIMATE_RETRY_SECONDS)


async def _fetch(start, end) -> tuple:
    """``start``/``end`` are (lat, lng). Returns (status, distance_m, duration_s, failure).
    Never raises."""
    try:
        route = await asyncio.wait_for(
            map_service.get_route_from_ola(start[0], start[1], end[0], end[1]),
            timeout=PROVIDER_CALL_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, map_service.RoutingProviderTimeout):
        logger.warning("corridor estimate: provider timeout")
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_TIMEOUT
    except map_service.RoutingProviderError:
        logger.warning("corridor estimate: provider error")
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_UNAVAILABLE
    except Exception as exc:  # noqa: BLE001 - the adapter must never raise
        logger.warning("corridor estimate: unexpected %s", type(exc).__name__)
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_UNAVAILABLE

    if route is None:
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_NO_ROUTE
    try:
        distance = int(route["distance_meters"])
        duration = int(route["duration_seconds"])
    except (KeyError, TypeError, ValueError):
        logger.warning("corridor estimate: malformed provider result")
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_UNAVAILABLE
    if distance < 0 or duration < 0:
        return EstimateStatus.UNVERIFIED, None, None, FAILURE_UNAVAILABLE
    return EstimateStatus.VERIFIED, distance, duration, None


def _apply(row: CorridorEstimate, result: tuple, checked_at_db: datetime) -> None:
    status, distance, duration, failure = result
    row.status = status
    row.distance_m = distance
    row.duration_s = duration
    row.failure = failure
    row.checked_at = checked_at_db


def cached_status(db: Session, origin_landmark_id: int, hub_id: int, direction) -> str:
    """Status of the cached estimate ("VERIFIED"/"UNVERIFIED") without ever calling
    the provider; "UNVERIFIED" when nothing is cached. Never raises."""
    try:
        row = (
            db.query(CorridorEstimate)
            .filter(
                CorridorEstimate.origin_landmark_id == origin_landmark_id,
                CorridorEstimate.hub_id == hub_id,
                CorridorEstimate.direction == Direction(_val(direction)),
            )
            .first()
        )
        return _val(row.status) if row is not None else EstimateStatus.UNVERIFIED.value
    except Exception:  # noqa: BLE001
        return EstimateStatus.UNVERIFIED.value


async def corridor_estimate(
    db: Session,
    origin_landmark,
    hub_landmark,
    direction,
    now: Optional[datetime] = None,
    release_transaction: bool = False,
) -> CorridorEstimate:
    """Cached estimate for one corridor and direction.

    TO_HUB routes campus point -> hub, FROM_HUB routes hub -> campus point.
    The returned row is attached to ``db`` when it could be persisted (the
    caller commits); otherwise it is a transient, UNVERIFIED object. Never raises.

    ``release_transaction=True`` COMMITS the session right before awaiting the
    provider so no DB transaction is held open across the network call. Only
    pass it when the caller has no uncommitted work it wants to keep pending.
    """
    now = campus_time.from_db(now) if now is not None else campus_time.utcnow()
    direction_enum = Direction(_val(direction))
    # Plain values up front: ORM instances expire when the session commits.
    origin_id, hub_id = origin_landmark.id, hub_landmark.id
    origin_pt = (origin_landmark.latitude, origin_landmark.longitude)
    hub_pt = (hub_landmark.latitude, hub_landmark.longitude)
    try:
        row = (
            db.query(CorridorEstimate)
            .filter(
                CorridorEstimate.origin_landmark_id == origin_id,
                CorridorEstimate.hub_id == hub_id,
                CorridorEstimate.direction == direction_enum,
            )
            .first()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("corridor estimate: cache read failed (%s)", type(exc).__name__)
        row = None

    if row is not None and _is_fresh(row, now):
        return row

    if direction_enum == Direction.TO_HUB:
        start, end = origin_pt, hub_pt
    else:
        start, end = hub_pt, origin_pt

    if release_transaction:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("corridor estimate: commit before provider call failed (%s)", type(exc).__name__)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            row = None   # whatever we had read is no longer trustworthy

    result = await _fetch(start, end)
    checked_at_db = campus_time.to_db(now)

    try:
        if row is not None:
            _apply(row, result, checked_at_db)
            db.flush()
            return row
        new_row = CorridorEstimate(
            origin_landmark_id=origin_id,
            hub_id=hub_id,
            direction=direction_enum,
        )
        _apply(new_row, result, checked_at_db)
        try:
            with db.begin_nested():
                db.add(new_row)
        except IntegrityError:
            # A concurrent request cached this corridor first: update that row.
            existing = (
                db.query(CorridorEstimate)
                .filter(
                    CorridorEstimate.origin_landmark_id == origin_id,
                    CorridorEstimate.hub_id == hub_id,
                    CorridorEstimate.direction == direction_enum,
                )
                .one()
            )
            _apply(existing, result, checked_at_db)
            db.flush()
            return existing
        return new_row
    except Exception as exc:  # noqa: BLE001 - never raise to the caller
        logger.warning("corridor estimate: cache write failed (%s)", type(exc).__name__)
        status, distance, duration, failure = result
        transient = CorridorEstimate(
            origin_landmark_id=origin_id,
            hub_id=hub_id,
            direction=direction_enum,
            status=status,
            distance_m=distance,
            duration_s=duration,
            failure=failure,
            checked_at=checked_at_db,
        )
        return transient
