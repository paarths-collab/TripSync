"""Real PostgreSQL regression cases for races missed by the SQLite harness."""

import asyncio
import os
import threading
from datetime import timedelta

import pytest
from sqlalchemy import event

from app.core import campus_time
from app.models import pooling_model as pm, campus_model as cm, user_model
from app.schemas import pooling_schema, campus_schema
from app.services import pooling_service, campus_suggestion_service, campus_request_service, campus_estimates, campus_party_service
from app.routes import campus_events_router
from tests.test_campus_party_postgres import pg  # noqa: F401
from tests.campus_party_helpers import race, seed_college, seed_user, seed_request, seed_party

pytestmark = pytest.mark.skipif(not os.environ.get("TRIPSYNC_TEST_PG_URL"),
                               reason="set TRIPSYNC_TEST_PG_URL to run PostgreSQL regression tests")

SEARCH = pooling_schema.PoolingRequestCreate(start_latitude=19, start_longitude=72,
    destination_latitude=20, destination_longitude=73, destination_name="Example")


def test_concurrent_first_searches_leave_one_live_request(pg):
    ids = seed_college(pg)
    for iteration in range(5):
        uid = seed_user(pg, ids["college_id"], f"same{iteration}")
        def search(db):
            return pooling_service.create_or_update_pooling_request(db, db.get(user_model.User, uid), SEARCH)
        outcomes, _ = race(pg, [search, search])
        assert outcomes == [200, 200], outcomes
        with pg() as db:
            live = db.query(pm.PoolingRequest).filter(
                pm.PoolingRequest.user_id == uid,
                pm.PoolingRequest.status.in_([pm.PoolingRequestStatus.ACTIVE, pm.PoolingRequestStatus.MATCHED]),
            ).all()
            assert len(live) == 1


def test_concurrent_approvals_of_legacy_duplicate_requests_allow_one_ride(pg):
    """Even pre-existing duplicate searches cannot give a participant two rides."""
    ids = seed_college(pg)
    uid = seed_user(pg, ids["college_id"], "same")
    proposals = []
    for i in range(2):
        other = seed_user(pg, ids["college_id"], f"partner{i}")
        with pg() as db:
            requests = [pm.PoolingRequest(user_id=u, status=pm.PoolingRequestStatus.ACTIVE,
                        **SEARCH.model_dump()) for u in (other, uid)]
            db.add_all(requests)
            db.flush()
            proposal = pm.PoolingConnection(sender_request_id=requests[0].id,
                         receiver_request_id=requests[1].id, status=pm.PoolingConnectionStatus.PENDING)
            db.add(proposal)
            db.commit()
            proposals.append(proposal.id)
    def approve(pid):
        return lambda db: pooling_service.respond_to_connection(db, pid, "approve", db.get(user_model.User, uid))
    outcomes, _ = race(pg, [approve(pid) for pid in proposals])
    assert sorted(outcomes) == [200, 409], outcomes
    with pg() as db:
        assert db.query(pm.PoolingRequest).filter_by(user_id=uid, status=pm.PoolingRequestStatus.CONNECTED).count() == 1


@pytest.mark.parametrize("cancel", [False, True])
def test_request_invalidation_during_suggestion_refresh_retries(pg, monkeypatch, cancel):
    ids = seed_college(pg)
    ua, ub = [seed_user(pg, ids["college_id"], key) for key in ("a", "b")]
    now = campus_time.utcnow()
    ra = seed_request(pg, ids, ua, now)
    seed_request(pg, ids, ub, now)
    async def route(*args):
        return {"distance_meters": 9000, "duration_seconds": 1200}
    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", route)
    with pg() as db:
        initial = asyncio.run(campus_suggestion_service.suggestions_for_request(db, db.get(user_model.User, ua), ra, now))
        assert len(initial["suggestions"]) == 1
    original = campus_suggestion_service._upsert_suggestion
    invalidated = False
    def invalidate_after_snapshot(db, existing, low, high, values):
        nonlocal invalidated
        if not invalidated:
            invalidated = True
            with pg() as writer:
                user = writer.get(user_model.User, ua)
                if cancel:
                    campus_request_service.cancel_request(writer, user, ra, now + timedelta(seconds=61))
                else:
                    campus_request_service.patch_request(writer, user, ra,
                        campus_schema.TravelRequestPatch(expected_version=1, latest_departure=now + timedelta(minutes=130)),
                        now + timedelta(seconds=61))
                writer.commit()
        return original(db, existing, low, high, values)
    monkeypatch.setattr(campus_suggestion_service, "_upsert_suggestion", invalidate_after_snapshot)
    with pg() as db:
        result = asyncio.run(campus_suggestion_service.suggestions_for_request(
            db, db.get(user_model.User, ua), ra, now + timedelta(seconds=61)))
        assert invalidated
        assert len(result["suggestions"]) == (0 if cancel else 1)
        assert db.get(cm.TravelRequest, ra).status == (cm.TravelRequestStatus.CANCELLED if cancel else cm.TravelRequestStatus.OPEN)


def test_event_snapshot_and_ack_do_not_advance_past_returned_party(pg):
    ids = seed_college(pg)
    ua, ub = [seed_user(pg, ids["college_id"], key) for key in ("a", "b")]
    now = campus_time.utcnow()
    reqs = [seed_request(pg, ids, u, now) for u in (ua, ub)]
    pid = seed_party(pg, ids, [ua, ub], reqs, now)
    engine = pg.kw["bind"]
    writer_started, writer_finished = threading.Event(), threading.Event()
    failures, threads = [], []
    def write():
        try:
            with pg() as writer:
                writer_started.set()
                asyncio.run(campus_party_service.update_cost_note(writer, writer.get(user_model.User, ua), pid,
                    campus_schema.PartyNotePatch(expected_version=1, cost_note="Changed Example")))
        except Exception as exc:
            failures.append(exc)
        finally:
            writer_finished.set()
    def between_snapshot_reads(conn, cursor, statement, params, ctx, many):
        if not threads and "FROM party_events" in statement:
            thread = threading.Thread(target=write)
            threads.append(thread)
            thread.start()
            assert writer_started.wait(timeout=5)
            # A versioned mutation cannot commit in the middle of this read.
            assert not writer_finished.wait(timeout=0.1)
    event.listen(engine, "before_cursor_execute", between_snapshot_reads)
    try:
        with pg() as reader:
            response = asyncio.run(campus_events_router.get_events(after_version=0, party_id=pid,
                                      db=reader, current_user=reader.get(user_model.User, ub)))
        assert response.latest_version == response.party.version == 1
        assert response.party.cost_note is None
        assert [e.version for e in response.events] == [1]
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        assert not failures, failures
        with pg() as reader:
            response = asyncio.run(campus_events_router.get_events(after_version=1, party_id=pid,
                                      db=reader, current_user=reader.get(user_model.User, ub)))
            assert response.latest_version == response.party.version == 2
            assert response.party.cost_note == "Changed Example"
            assert [e.version for e in response.events] == [2]
    finally:
        event.remove(engine, "before_cursor_execute", between_snapshot_reads)
        for thread in threads:
            thread.join(timeout=10)
