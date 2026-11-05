"""Opt-in Postgres concurrency tests for campus requests and suggestions.

Skipped unless TRIPSYNC_TEST_PG_URL is set (same setup as
tests/test_campus_party_postgres.py; TRIPSYNC_TEST_PG_ITERATIONS controls the
number of rounds, default 5). Every racing operation runs the real service
function in its own thread with its own Session, released together by a
Barrier (``tests.campus_party_helpers.race``). Real clock, fictional data.

What these pin down:
- PATCH takes the user row with FOR NO KEY UPDATE, so it never deadlocks with
  operations that hold request locks and then insert rows referencing the user
  (proposals, party events, outbox rows);
- one user's concurrent creates respect MAX_OPEN_REQUESTS_PER_USER and the
  no-overlap rule;
- simultaneous suggestion searches never fail and never duplicate rows.
"""

import os
import uuid
from datetime import timedelta

import pytest

from app.core import campus_rules, campus_time
from app.models import campus_model as cm
from app.models import user_model
from app.schemas import campus_schema as schemas
from app.services import campus_estimates
from app.services import campus_party_service as svc
from app.services import campus_request_service, campus_suggestion_service
from tests.campus_party_helpers import (
    race, seed_college, seed_party, seed_request, seed_user,
)
from tests.test_campus_party_postgres import pg  # noqa: F401  (throwaway-schema fixture)

PG_URL = os.environ.get("TRIPSYNC_TEST_PG_URL")
ITERATIONS = int(os.environ.get("TRIPSYNC_TEST_PG_ITERATIONS", "5"))

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TRIPSYNC_TEST_PG_URL to run the Postgres concurrency tests"
)

RS = cm.TravelRequestStatus
PS = cm.ProposalState


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def world(pg):  # noqa: F811
    """make(keys) -> (users, reqs, now): fresh users, one OPEN request each
    (window now+10..now+120) in a shared college."""
    ids = seed_college(pg)

    def make(*keys):
        tag = uuid.uuid4().hex[:8]
        now = campus_time.utcnow()
        users = {k: seed_user(pg, ids["college_id"], k, tag) for k in keys}
        reqs = {k: seed_request(pg, ids, users[k], now) for k in keys}
        return users, reqs, now

    make.ids = ids
    return make


@pytest.fixture
def fake_provider(monkeypatch):
    async def fake(slat, slng, elat, elng):
        return {"distance_meters": 9000, "duration_seconds": 1500}

    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", fake)


# ----------------------------------------------------------------- jobs
def _uow(db, fn):
    """Coroutine that runs ``fn`` and commits (rolling back on any exception)."""
    async def run():
        try:
            result = fn()
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    return run()


def patch_job(request_id, user_id, latest):
    body = schemas.TravelRequestPatch(expected_version=1, latest_departure=latest)

    def job(db):
        user = db.get(user_model.User, user_id)
        return _uow(db, lambda: campus_request_service.patch_request(
            db, user, request_id, body, campus_time.utcnow()))
    return job


def create_job(ids, user_id, start, end):
    now = campus_time.utcnow()
    body = schemas.TravelRequestCreate(
        origin_landmark_id=ids["campus"], hub_id=ids["hub"], direction="TO_HUB",
        earliest_departure=now + timedelta(minutes=start),
        latest_departure=now + timedelta(minutes=end), timezone="Asia/Kolkata")

    def job(db):
        user = db.get(user_model.User, user_id)
        return _uow(db, lambda: campus_request_service.create_request(
            db, user, body, campus_time.utcnow()))
    return job


def cancel_party_job(party_id, user_id, key):
    body = schemas.PartyCancel(idempotency_key=key)

    def job(db):
        return svc.cancel_party(db, db.get(user_model.User, user_id), party_id, body)
    return job


def report_job(party_id, user_id):
    body = schemas.ReportBody(outcome="COMPLETED")

    def job(db):
        return svc.report_outcome(db, db.get(user_model.User, user_id), party_id, body)
    return job


def propose_job(suggestion_id, user_id):
    body = schemas.ConnectionCreate()

    def job(db):
        return svc.create_proposal(db, db.get(user_model.User, user_id), suggestion_id, body)
    return job


def search_job(request_id, user_id):
    def job(db):
        user = db.get(user_model.User, user_id)
        return campus_suggestion_service.suggestions_for_request(
            db, user, request_id, campus_time.utcnow())
    return job


def seed_suggestion(sf, req_a, req_b, now):
    low, high = campus_rules.pair_key(req_a, req_b)
    db = sf()
    try:
        row = cm.PairSuggestion(
            request_low_id=low, request_high_id=high, rule_version=campus_rules.RULE_VERSION,
            reason=cm.SuggestionReason.WINDOW_OVERLAP,
            feasible_start=campus_time.to_db(now + timedelta(minutes=10)),
            feasible_end=campus_time.to_db(now + timedelta(minutes=120)),
            estimate_status=cm.EstimateStatus.UNVERIFIED, estimate_failure="timeout",
            warnings=[], valid_until=campus_time.to_db(now + timedelta(minutes=15)),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


# ------------------------------------------------------------------- tests
def test_pg_patch_racing_cancel_party(pg, world):  # noqa: F811
    """Bob cancels the party (request locks, then event/outbox rows referencing
    Alice) while Alice PATCHes her reserved request."""
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        party_id = seed_party(pg, world.ids, [users["alice"], users["bob"]],
                              [reqs["alice"], reqs["bob"]], now)
        outcomes, details = race(pg, [
            cancel_party_job(party_id, users["bob"], "kc"),
            patch_job(reqs["alice"], users["alice"], now + timedelta(minutes=150)),
        ])
        assert outcomes[0] == 200, (outcomes, details)
        assert outcomes[1] in (200, 409), (outcomes, details)    # never an ERROR / deadlock
        db = pg()
        try:
            assert db.get(cm.TravelParty, party_id).state == cm.PartyState.CANCELLED
            cancelled = db.query(cm.PartyEvent).filter_by(
                party_id=party_id, event_type="PARTY_CANCELLED").count()
            assert cancelled == 1
            assert db.get(cm.TravelRequest, reqs["alice"]).status == RS.OPEN   # released by Bob's cancel
        finally:
            db.close()


def test_pg_patch_racing_report_outcome(pg, world):  # noqa: F811
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        party_id = seed_party(pg, world.ids, [users["alice"], users["bob"]],
                              [reqs["alice"], reqs["bob"]], now, departure_min=-5)
        outcomes, details = race(pg, [
            report_job(party_id, users["bob"]),
            patch_job(reqs["alice"], users["alice"], now + timedelta(minutes=150)),
        ])
        assert outcomes[0] == 200, (outcomes, details)
        assert outcomes[1] == 409, (outcomes, details)   # alice's request is RESERVED: not editable
        assert details[1]["code"] == "request_not_open"
        db = pg()
        try:
            assert db.query(cm.PartyEvent).filter_by(
                party_id=party_id, event_type="REPORT_RECORDED").count() == 1
            assert db.get(cm.TravelRequest, reqs["alice"]).version == 1
        finally:
            db.close()


def test_pg_patch_racing_create_proposal(pg, world):  # noqa: F811
    """Bob proposes to Alice (locks both requests, inserts a proposal referencing
    Alice) while Alice PATCHes R_a."""
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        sid = seed_suggestion(pg, reqs["alice"], reqs["bob"], now)
        outcomes, details = race(pg, [
            propose_job(sid, users["bob"]),
            patch_job(reqs["alice"], users["alice"], now + timedelta(minutes=150)),
        ])
        # 404: the edit ran first and deleted the suggestion; 409: no longer eligible
        assert outcomes[0] in (200, 404, 409), (outcomes, details)
        assert outcomes[1] == 200, (outcomes, details)
        db = pg()
        try:
            alice_req = db.get(cm.TravelRequest, reqs["alice"])
            assert alice_req.version == 2 and alice_req.status == RS.OPEN
            proposals = db.query(cm.ConnectionProposal).filter(
                cm.ConnectionProposal.proposer_request_id == reqs["bob"]).all()
            assert len(proposals) == (1 if outcomes[0] == 200 else 0)
            for p in proposals:
                if p.state == PS.PENDING:
                    # created after the edit: it must carry the edited version
                    assert p.recipient_request_version == alice_req.version
                else:
                    # created before the edit: the edit expired it
                    assert p.state == PS.EXPIRED
        finally:
            db.close()


def test_pg_same_user_creates_respect_the_open_request_limit(pg, world):  # noqa: F811
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice")
        uid = users["alice"]
        # alice already has 1 request (10..120) -> room for exactly 2 more
        racers = [create_job(world.ids, uid, 200 + 100 * i, 260 + 100 * i) for i in range(4)]
        outcomes, details = race(pg, racers)
        assert sorted(outcomes) == [200, 200, 409, 409], (outcomes, details)
        assert {d["code"] for d in details if d} == {"max_open_requests"}
        db = pg()
        try:
            live = db.query(cm.TravelRequest).filter(
                cm.TravelRequest.user_id == uid,
                cm.TravelRequest.status.in_([RS.OPEN, RS.RESERVED])).count()
            assert live == campus_rules.MAX_OPEN_REQUESTS_PER_USER
        finally:
            db.close()


def test_pg_same_user_overlapping_creates_admit_only_one(pg, world):  # noqa: F811
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice")
        uid = users["alice"]
        outcomes, details = race(pg, [create_job(world.ids, uid, 300, 360),
                                      create_job(world.ids, uid, 330, 390)])
        assert sorted(outcomes) == [200, 409], (outcomes, details)
        assert [d for d in details if d][0]["code"] == "overlapping_request"


def test_pg_create_and_patch_by_one_user_cannot_overlap(pg, world):  # noqa: F811
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice")
        uid = users["alice"]
        seed_request(pg, world.ids, uid, now, start_min=200, end_min=260)
        # the edit reaches into the second request's window while a create lands elsewhere
        outcomes, details = race(pg, [
            patch_job(reqs["alice"], uid, now + timedelta(minutes=230)),   # 10..230 overlaps 200..260
            create_job(world.ids, uid, 300, 360),                          # fine on its own
        ])
        assert outcomes[0] == 409 and details[0]["code"] == "overlapping_request", (outcomes, details)
        assert outcomes[1] == 200, (outcomes, details)
        db = pg()
        try:
            windows = sorted(
                (r.earliest_departure, r.latest_departure) for r in db.query(cm.TravelRequest).filter(
                    cm.TravelRequest.user_id == uid, cm.TravelRequest.status == RS.OPEN))
            assert all(a[1] < b[0] for a, b in zip(windows, windows[1:])), windows
        finally:
            db.close()


def test_pg_three_simultaneous_suggestion_searches(pg, world, fake_provider):  # noqa: F811
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob", "carol")
        outcomes, details = race(pg, [search_job(reqs[k], users[k]) for k in ("alice", "bob", "carol")])
        assert outcomes == [200, 200, 200], (outcomes, details)
        db = pg()
        try:
            ids = sorted(reqs.values())
            rows = db.query(cm.PairSuggestion).filter(
                cm.PairSuggestion.request_low_id.in_(ids), cm.PairSuggestion.request_high_id.in_(ids)).all()
            keys = [(r.request_low_id, r.request_high_id, r.rule_version) for r in rows]
            assert len(keys) == len(set(keys)) == 3
            assert sorted((r.request_low_id, r.request_high_id) for r in rows) == [
                (ids[0], ids[1]), (ids[0], ids[2]), (ids[1], ids[2])]
            assert db.query(cm.CorridorEstimate).count() == 1
            for rid in reqs.values():           # searching never touches a request
                r = db.get(cm.TravelRequest, rid)
                assert (r.status, r.version) == (RS.OPEN, 1)
        finally:
            db.close()

        # a second round of simultaneous searches is a no-op for the rows
        outcomes, details = race(pg, [search_job(reqs[k], users[k]) for k in ("alice", "bob", "carol")])
        assert outcomes == [200, 200, 200], (outcomes, details)
        db = pg()
        try:
            assert db.query(cm.PairSuggestion).filter(
                cm.PairSuggestion.request_low_id.in_(list(reqs.values())),
                cm.PairSuggestion.request_high_id.in_(list(reqs.values()))).count() == 3
        finally:
            db.close()
