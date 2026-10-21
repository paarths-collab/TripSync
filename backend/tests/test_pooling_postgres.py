"""Opt-in Postgres concurrency tests for the pooling lifecycle.

SQLite serializes writers and ignores SELECT ... FOR UPDATE, so races and deadlocks
(the lock-ordering rule in pooling_service) can only be shaken out on Postgres.

These tests are SKIPPED unless TRIPSYNC_TEST_PG_URL is set, e.g.

    docker run --rm -d -p 55432:5432 -e POSTGRES_USER=tripsync \
        -e POSTGRES_PASSWORD=tripsync -e POSTGRES_DB=tripsync_test postgres:15-alpine
    cd backend && TRIPSYNC_TEST_PG_URL=postgresql+psycopg2://tripsync:tripsync@127.0.0.1:55432/tripsync_test \
        .venv/bin/python -m pytest -q tests/test_pooling_postgres.py

Each test creates (and finally drops) a throwaway schema inside that database, so
the database may be reused. Optional: TRIPSYNC_TEST_PG_ITERATIONS (default 5).

Each racing operation runs in its own thread with its own Session, calling the real
service functions through asyncio.run, lined up with a threading.Barrier. Fictional
data only.
"""

import asyncio
import os
import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models import pooling_model, user_model
from app.schemas import pooling_schema
from app.services import pooling_service as svc

PG_URL = os.environ.get("TRIPSYNC_TEST_PG_URL")
ITERATIONS = int(os.environ.get("TRIPSYNC_TEST_PG_ITERATIONS", "5"))

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TRIPSYNC_TEST_PG_URL to run the Postgres concurrency tests"
)

RS = pooling_model.PoolingRequestStatus
CS = pooling_model.PoolingConnectionStatus
OPEN = (RS.ACTIVE, RS.MATCHED)


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def pg():
    """Session factory bound to a throwaway schema on the Postgres under test."""
    schema = f"tripsync_t_{uuid.uuid4().hex[:10]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        PG_URL,
        pool_size=8,
        max_overflow=8,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def world(pg):
    """Factory for isolated fixtures: fresh users/requests for each iteration."""
    db = pg()
    college = user_model.College(name="DJSCE")
    db.add(college)
    db.commit()
    college_id = college.id
    db.close()

    def make(request_statuses, connections=()):
        """request_statuses: {"a": RS.MATCHED, ...} -> one user+request per key.
        connections: [(sender_key, receiver_key, status), ...].
        Returns ({key: user_id}, {key: request_id}, [connection_id, ...])."""
        tag = uuid.uuid4().hex[:8]
        db = pg()
        try:
            uids, rids, cids = {}, {}, []
            for key, status in request_statuses.items():
                user = user_model.User(
                    email=f"{key}.{tag}@example.test",
                    full_name=f"{key.title()} Example",
                    hashed_password="not-a-real-hash",
                    college_id=college_id,
                )
                db.add(user)
                db.flush()
                req = pooling_model.PoolingRequest(
                    user_id=user.id, status=status,
                    start_latitude=19.07, start_longitude=72.87,
                    destination_latitude=19.12, destination_longitude=72.90,
                    destination_name="Fictional Hall",
                )
                db.add(req)
                db.flush()
                uids[key], rids[key] = user.id, req.id
            for sender, receiver, status in connections:
                conn = pooling_model.PoolingConnection(
                    sender_request_id=rids[sender], receiver_request_id=rids[receiver], status=status
                )
                db.add(conn)
                db.flush()
                cids.append(conn.id)
            db.commit()
            return uids, rids, cids
        finally:
            db.close()

    return make


# ----------------------------------------------------------------- helpers
def race(pg, jobs):
    """Run each job(db) -> coroutine in its own thread/session, released together by
    a Barrier. Returns one outcome per job: 200 on success, the HTTP status of an
    HTTPException, or "ERROR: ..." (a deadlock/serialization failure would land here)."""
    barrier = threading.Barrier(len(jobs))
    outcomes = [None] * len(jobs)

    def worker(index, job):
        db = pg()
        try:
            coro = job(db)  # load users etc. before the starting gun
            barrier.wait(timeout=60)
            asyncio.run(coro)
            outcomes[index] = 200
        except HTTPException as exc:
            outcomes[index] = exc.status_code
        except Exception as exc:  # noqa: BLE001
            outcomes[index] = f"ERROR: {type(exc).__name__}: {str(exc)[:200]}"
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
        assert not t.is_alive(), "worker hung (deadlock?)"
    return outcomes


def req_status(pg, request_id):
    db = pg()
    try:
        return db.get(pooling_model.PoolingRequest, request_id).status
    finally:
        db.close()


def conn_status(pg, connection_id):
    db = pg()
    try:
        return db.get(pooling_model.PoolingConnection, connection_id).status
    finally:
        db.close()


def respond(connection_id, user_id, action="approve"):
    def job(db):
        return svc.respond_to_connection(db, connection_id, action, db.get(user_model.User, user_id))
    return job


def cancel(request_id, user_id):
    def job(db):
        return svc.cancel_pooling_request(db, request_id, db.get(user_model.User, user_id))
    return job


def send(sender_request_id, receiver_request_id, user_id):
    def job(db):
        return svc.send_connection_request(
            db, sender_request_id, receiver_request_id, db.get(user_model.User, user_id)
        )
    return job


def new_search(user_id):
    body = pooling_schema.PoolingRequestCreate(
        start_latitude=19.07, start_longitude=72.87,
        destination_latitude=19.12, destination_longitude=72.90,
        destination_name="Fictional Hall",
    )

    def job(db):
        return svc.create_or_update_pooling_request(db, db.get(user_model.User, user_id), body)
    return job


# ------------------------------------------------------------------- tests
def test_pg_competing_approvals_exactly_one_wins(pg, world):
    for _ in range(ITERATIONS):
        uids, rids, (c_alice, c_carol) = world(
            {"alice": RS.MATCHED, "carol": RS.MATCHED, "bob": RS.MATCHED},
            [("alice", "bob", CS.PENDING), ("carol", "bob", CS.PENDING)],
        )
        outcomes = race(pg, [respond(c_alice, uids["bob"]), respond(c_carol, uids["bob"])])

        assert sorted(outcomes, key=str) == [200, 409], outcomes
        statuses = sorted([conn_status(pg, c_alice), conn_status(pg, c_carol)], key=lambda s: s.value)
        assert statuses == [CS.APPROVED, CS.REJECTED]
        assert req_status(pg, rids["bob"]) == RS.CONNECTED
        partners_connected = [k for k in ("alice", "carol") if req_status(pg, rids[k]) == RS.CONNECTED]
        assert len(partners_connected) == 1
        loser = "carol" if partners_connected == ["alice"] else "alice"
        assert req_status(pg, rids[loser]) == RS.MATCHED


def test_pg_both_partners_cancel_ride_simultaneously(pg, world):
    for _ in range(ITERATIONS):
        uids, rids, (cid,) = world(
            {"alice": RS.CONNECTED, "bob": RS.CONNECTED}, [("alice", "bob", CS.APPROVED)]
        )
        outcomes = race(pg, [cancel(rids["alice"], uids["alice"]), cancel(rids["bob"], uids["bob"])])

        assert outcomes == [200, 200], outcomes
        assert req_status(pg, rids["alice"]) == RS.CANCELLED
        assert req_status(pg, rids["bob"]) == RS.CANCELLED
        assert conn_status(pg, cid) == CS.APPROVED


@pytest.mark.parametrize("direction", ["same", "reverse"])
def test_pg_concurrent_duplicate_sends_create_one_pending_row(pg, world, direction):
    for _ in range(ITERATIONS):
        uids, rids, _ = world({"alice": RS.MATCHED, "bob": RS.MATCHED})
        second = (
            send(rids["alice"], rids["bob"], uids["alice"])
            if direction == "same"
            else send(rids["bob"], rids["alice"], uids["bob"])
        )
        outcomes = race(pg, [send(rids["alice"], rids["bob"], uids["alice"]), second])

        assert sorted(outcomes, key=str) == [200, 400], outcomes
        db = pg()
        try:
            ids = [rids["alice"], rids["bob"]]
            rows = db.query(pooling_model.PoolingConnection).filter(
                pooling_model.PoolingConnection.sender_request_id.in_(ids),
                pooling_model.PoolingConnection.receiver_request_id.in_(ids),
            ).all()
            assert [r.status for r in rows] == [CS.PENDING]
        finally:
            db.close()


@pytest.mark.parametrize("racer", ["sender", "receiver"])
def test_pg_approve_racing_a_new_search_never_leaves_connected_plus_active(pg, world, racer):
    for _ in range(ITERATIONS):
        uids, rids, (cid,) = world(
            {"alice": RS.MATCHED, "bob": RS.MATCHED}, [("alice", "bob", CS.PENDING)]
        )
        searcher = uids["alice"] if racer == "sender" else uids["bob"]
        outcomes = race(pg, [respond(cid, uids["bob"]), new_search(searcher)])

        assert all(o in (200, 409) for o in outcomes), outcomes
        assert outcomes.count(200) == 1, outcomes  # exactly one of the two wins

        db = pg()
        try:
            for user_id in (uids["alice"], uids["bob"]):
                statuses = [
                    r.status for r in db.query(pooling_model.PoolingRequest).filter_by(user_id=user_id)
                ]
                assert not (RS.CONNECTED in statuses and any(s in OPEN for s in statuses)), statuses
            if outcomes[0] == 200:  # approval won: nobody started a new search
                assert req_status(pg, rids["alice"]) == RS.CONNECTED
                assert req_status(pg, rids["bob"]) == RS.CONNECTED
            else:  # the new search won: the invite died with the old request
                assert conn_status(pg, cid) == CS.REJECTED
        finally:
            db.close()
