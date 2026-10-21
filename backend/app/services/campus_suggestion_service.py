# backend/app/services/campus_suggestion_service.py
"""Pair suggestions for a travel request.

A suggestion is only information: generating, refreshing or reading
suggestions never changes any request's status or version, and never removes a
request from anybody else's search. Eligibility is decided by
``campus_rules.eligible_pair`` (overlapping departure windows), never by
creation time.

Candidate lookup is an indexed corridor query (college, origin, hub, direction,
status = OPEN) bounded by the departure window, so it never scans all requests.
Contact details of other users are never read or returned.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import campus_rules, campus_time
from app.models.campus_model import (
    ConnectionProposal,
    EstimateStatus,
    PairSuggestion,
    ProposalState,
    SuggestionReason,
    TravelParty,
    PartyState,
    TravelRequest,
    TravelRequestStatus,
)
from app.models.user_model import User
from app.schemas import campus_schema
from app.services import campus_estimates, campus_request_service

logger = logging.getLogger(__name__)

# Upper bound on candidates examined per call (protects against a hot corridor).
MAX_CANDIDATES = 200
# A stored valid_until is only rewritten when the new value is at least this much
# later, so repeated GETs do not rewrite every suggestion row each time.
VALID_UNTIL_REFRESH = timedelta(seconds=60)

_EPOCH_JULIAN_DAY = 2440587.5


def _val(x):
    return getattr(x, "value", x)


def _epoch_seconds(db: Session, column):
    """SQL expression: seconds since the Unix epoch for a naive-UTC column."""
    if db.get_bind().dialect.name == "sqlite":
        return (func.julianday(column) - _EPOCH_JULIAN_DAY) * 86400.0
    return func.extract("epoch", column)


def find_candidates(
    db: Session, me: TravelRequest, now: datetime
) -> Tuple[List[TravelRequest], bool]:
    """OPEN requests on the same corridor/direction whose windows could pair with ``me``.

    Returns ``(candidates, truncated)``. The SQL bound uses the widest possible
    reach (two flexibility margins); ``eligible_pair`` makes the final decision.
    When more than ``MAX_CANDIDATES`` match, the ones whose window midpoint is
    closest to the caller's are kept (then lowest id), so a busy corridor does not
    permanently hide later requests; ``truncated`` is True in that case.
    """
    now_db = campus_time.to_db(now)
    reach = timedelta(minutes=2 * campus_rules.FLEX_MINUTES)
    cap = MAX_CANDIDATES
    my_mid = (
        me.earliest_departure.replace(tzinfo=campus_time.UTC).timestamp()
        + me.latest_departure.replace(tzinfo=campus_time.UTC).timestamp()
    ) / 2.0
    midpoint = (
        _epoch_seconds(db, TravelRequest.earliest_departure)
        + _epoch_seconds(db, TravelRequest.latest_departure)
    ) / 2.0
    rows = (
        db.query(TravelRequest)
        .filter(
            TravelRequest.college_id == me.college_id,
            TravelRequest.origin_landmark_id == me.origin_landmark_id,
            TravelRequest.hub_id == me.hub_id,
            TravelRequest.direction == me.direction,
            TravelRequest.status == TravelRequestStatus.OPEN,
            TravelRequest.latest_departure > now_db,
            TravelRequest.expires_at > now_db,
            TravelRequest.user_id != me.user_id,
            TravelRequest.earliest_departure <= me.latest_departure + reach,
            TravelRequest.latest_departure >= me.earliest_departure - reach,
        )
        .order_by(func.abs(midpoint - my_mid), TravelRequest.id)
        .limit(cap + 1)
        .all()
    )
    return rows[:cap], len(rows) > cap


def _suggestion_values(me, other, verdict, estimate, now: datetime, valid_until: datetime) -> dict:
    departure = max(verdict.feasible_start, campus_time.from_db(now))
    return {
        "reason": SuggestionReason(verdict.reason),
        "feasible_start": campus_time.to_db(verdict.feasible_start),
        "feasible_end": campus_time.to_db(verdict.feasible_end),
        "estimate_status": EstimateStatus(_val(estimate.status)),
        "estimate_distance_m": estimate.distance_m,
        "estimate_duration_s": estimate.duration_s,
        "estimate_failure": estimate.failure,
        "estimate_checked_at": estimate.checked_at,
        "warnings": campus_rules.deadline_warnings(me, other, departure, estimate),
        "valid_until": valid_until,
    }


def _changed_fields(row: PairSuggestion, values: dict) -> dict:
    """Fields of ``values`` that differ from the stored row (valid_until is only
    rewritten when it moves forward by at least VALID_UNTIL_REFRESH)."""
    changes = {}
    for key, new in values.items():
        old = getattr(row, key)
        if key == "valid_until":
            if old is None or new - old >= VALID_UNTIL_REFRESH:
                changes[key] = new
        elif _val(old) != _val(new):
            changes[key] = new
    return changes


def _upsert_suggestion(
    db: Session,
    existing: Dict[Tuple[int, int], PairSuggestion],
    low: int,
    high: int,
    values: dict,
) -> PairSuggestion:
    """Insert or refresh one row; unchanged rows are not written at all.

    Callers invoke this in ascending (low, high) order and every write is
    flushed immediately, so concurrent searchers always touch rows in the same
    order (no lock cycles between three or more simultaneous searchers).
    """
    row = existing.get((low, high))
    if row is None:
        row = PairSuggestion(
            request_low_id=low,
            request_high_id=high,
            rule_version=campus_rules.RULE_VERSION,
            **values,
        )
        try:
            with db.begin_nested():
                db.add(row)
            return row
        except IntegrityError:
            # A concurrent call created the same (low, high, rule_version) row.
            row = (
                db.query(PairSuggestion)
                .filter(
                    PairSuggestion.request_low_id == low,
                    PairSuggestion.request_high_id == high,
                    PairSuggestion.rule_version == campus_rules.RULE_VERSION,
                )
                .populate_existing()
                .one()
            )
    changes = _changed_fields(row, values)
    if changes:
        for key, new in changes.items():
            setattr(row, key, new)
        db.flush()
    return row


async def suggestions_for_request(
    db: Session, user: User, request_id: int, now: datetime
) -> dict:
    """Compute, persist (idempotently) and return the suggestions for the caller's request."""
    # Owner-only: 404 for unknown ids and other users' requests alike.
    campus_request_service.get_own_request(db, user, request_id)
    campus_request_service.expire_stale(db, now)
    db.commit()

    me = campus_request_service.get_own_request(db, user, request_id)
    me_id, user_id, tz_name = me.id, user.id, me.timezone

    if me.status != TravelRequestStatus.OPEN:
        # Nothing to suggest, so do not spend a provider call on it.
        status = campus_estimates.cached_status(db, me.origin_landmark_id, me.hub_id, me.direction)
        db.commit()
        return campus_schema.SuggestionsResponse(
            request_id=me_id, estimate_status=status, suggestions=[]
        ).model_dump(mode="json")

    # The adapter commits before awaiting the provider: no transaction is held
    # open across the network call.
    estimate = await campus_estimates.corridor_estimate(
        db, me.origin_landmark, me.hub, me.direction, now, release_transaction=True
    )
    estimate_status = _val(estimate.status)

    db.refresh(me)   # the request may have changed while we waited on the provider
    if me.status != TravelRequestStatus.OPEN:
        db.commit()
        return campus_schema.SuggestionsResponse(
            request_id=me_id, estimate_status=estimate_status, suggestions=[]
        ).model_dump(mode="json")

    candidates, truncated = find_candidates(db, me, now)
    eligible: List[Tuple[TravelRequest, campus_rules.Eligibility]] = []
    for other in candidates:
        verdict = campus_rules.eligible_pair(me, other, now)
        if verdict.ok:
            eligible.append((other, verdict))
    # Fixed global write order: ascending (low, high).
    eligible.sort(key=lambda ov: campus_rules.pair_key(me_id, ov[0].id))

    valid_until = campus_time.to_db(now + timedelta(minutes=campus_rules.SUGGESTION_TTL_MINUTES))
    existing = {
        (s.request_low_id, s.request_high_id): s
        for s in db.query(PairSuggestion)
        .filter(
            PairSuggestion.rule_version == campus_rules.RULE_VERSION,
            or_(PairSuggestion.request_low_id == me_id, PairSuggestion.request_high_id == me_id),
        )
        .all()
    }

    pairs: List[Tuple[TravelRequest, PairSuggestion]] = []
    for other, verdict in eligible:
        low, high = campus_rules.pair_key(me_id, other.id)
        values = _suggestion_values(me, other, verdict, estimate, now, valid_until)
        pairs.append((other, _upsert_suggestion(db, existing, low, high, values)))
    db.flush()

    # Proposal info (pending, or accepted with a party still in force).
    proposals: Dict[Tuple[int, int], ConnectionProposal] = {}
    if pairs:
        rows = (
            db.query(ConnectionProposal)
            .outerjoin(TravelParty, TravelParty.id == ConnectionProposal.party_id)
            .filter(
                or_(
                    ConnectionProposal.pair_low_request_id == me_id,
                    ConnectionProposal.pair_high_request_id == me_id,
                ),
                or_(
                    ConnectionProposal.state == ProposalState.PENDING,
                    (ConnectionProposal.state == ProposalState.ACCEPTED)
                    & (TravelParty.state == PartyState.AGREED),
                ),
            )
            .order_by(ConnectionProposal.id)
            .all()
        )
        for proposal in rows:
            proposals[(proposal.pair_low_request_id, proposal.pair_high_request_id)] = proposal

    users = {
        u.id: u
        for u in db.query(User.id, User.full_name)
        .filter(User.id.in_([o.user_id for o, _ in pairs] or [-1]))
        .all()
    }

    items = []
    for other, row in sorted(pairs, key=lambda p: (p[1].feasible_start, p[0].id)):
        low, high = campus_rules.pair_key(me_id, other.id)
        # users[...] is a (id, full_name) row: exactly the two fields exposed.
        items.append(
            campus_schema.SuggestionOut.build(
                row,
                users[other.user_id],
                other,
                tz_name,
                proposal=proposals.get((low, high)),
                viewer_id=user_id,
            )
        )

    db.commit()
    return campus_schema.SuggestionsResponse(
        request_id=me_id, estimate_status=estimate_status, suggestions=items, truncated=truncated
    ).model_dump(mode="json")
