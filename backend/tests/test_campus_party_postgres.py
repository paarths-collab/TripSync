"""Opt-in Postgres concurrency tests for campus connections and parties.

SQLite serializes writers and ignores SELECT ... FOR UPDATE, so lock-ordering
bugs, lost updates and deadlocks can only be shaken out on Postgres. These tests
are SKIPPED unless TRIPSYNC_TEST_PG_URL is set, e.g.

    docker run --rm -d -p 55432:5432 -e POSTGRES_USER=tripsync \
        -e POSTGRES_PASSWORD=tripsync -e POSTGRES_DB=tripsync_test postgres:15-alpine
    cd backend && TRIPSYNC_TEST_PG_URL=postgresql+psycopg2://tripsync:tripsync@127.0.0.1:55432/tripsync_test \
        .venv/bin/python -m pytest -q tests/test_campus_party_postgres.py

Each test creates (and finally drops) a throwaway schema, so the database may be
reused. Optional: TRIPSYNC_TEST_PG_ITERATIONS (default 5).

Every racing operation runs in its own thread with its own Session, calling the
real service functions through asyncio.run, lined up with a threading.Barrier.
Time is the real clock. Fictional data only.

(Dry run: a ``sqlite:///...`` URL also works and exercises the same assertions
on a file-backed SQLite database.)
"""

import os
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core import campus_time
from app.db.database import Base
from app.models import campus_model as cm
from app.models import user_model
from app.schemas import campus_schema as schemas
from app.services import campus_events, campus_request_service
from app.services import campus_party_service as svc
from tests.campus_party_helpers import (
    race, seed_college, seed_party, seed_proposal, seed_request, seed_user,
)

PG_URL = os.environ.get("TRIPSYNC_TEST_PG_URL")
ITERATIONS = int(os.environ.get("TRIPSYNC_TEST_PG_ITERATIONS", "5"))

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TRIPSYNC_TEST_PG_URL to run the Postgres concurrency tests"
)

RS = cm.TravelRequestStatus
PS = cm.ProposalState


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def pg(tmp_path):
    """Session factory bound to a throwaway schema on the database under test."""
    if PG_URL.startswith("sqlite"):  # dry run
        engine = create_engine(
            f"sqlite:///{tmp_path / 'dry.db'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        # SQLite has no row locks: BEGIN IMMEDIATE (whole-transaction write lock)
        # emulates the serialization that SELECT ... FOR UPDATE gives on Postgres.
        @event.listens_for(engine, "connect")
        def _no_driver_begin(dbapi_connection, _):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def _begin_immediate(conn):
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        Base.metadata.create_all(bind=engine)
        try:
            yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
        finally:
            engine.dispose()
        return

    schema = f"tripsync_c_{uuid.uuid4().hex[:10]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        PG_URL, pool_size=8, max_overflow=8,
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
    """make(keys) -> (ids, {key: user_id}, {key: request_id}): fresh users and one
    OPEN request each (window now+10..now+120) in a shared college."""
    ids = seed_college(pg)

    def make(*keys):
        tag = uuid.uuid4().hex[:8]
        now = campus_time.utcnow()
        users = {k: seed_user(pg, ids["college_id"], k, tag) for k in keys}
        reqs = {k: seed_request(pg, ids, users[k], now) for k in keys}
        return users, reqs, now

    make.ids = ids
    return make


# ----------------------------------------------------------------- helpers
def accept_job(proposal_id, user_id, key):
    body = schemas.ConnectionAccept(expected_version=1, idempotency_key=key)

    def job(db):
        return svc.accept_proposal(db, db.get(user_model.User, user_id), proposal_id, body)
    return job


def cancel_job(party_id, user_id, key):
    body = schemas.PartyCancel(idempotency_key=key)

    def job(db):
        return svc.cancel_party(db, db.get(user_model.User, user_id), party_id, body)
    return job


def approve_job(party_id, change_id, user_id, expected_version):
    def job(db):
        return svc.decide_change(db, db.get(user_model.User, user_id), party_id, change_id,
                                 action="approve", expected_party_version=expected_version)
    return job


def patch_request_job(request_id, user_id, new_latest):
    body = schemas.TravelRequestPatch(expected_version=1, latest_departure=new_latest)

    def job(db):
        async def run():
            try:
                campus_request_service.patch_request(
                    db, db.get(user_model.User, user_id), request_id, body, campus_time.utcnow())
                db.commit()
            except Exception:
                db.rollback()
                raise
        return run()
    return job


def only(db, model, **filters):
    return db.query(model).filter_by(**filters).all()


def check_event_log(db, party_id):
    """Event versions are exactly 1..n (no gap, no duplicate) and match party.version."""
    versions = [e.version for e in
                db.query(cm.PartyEvent).filter_by(party_id=party_id).order_by(cm.PartyEvent.version)]
    assert versions == list(range(1, len(versions) + 1)), versions
    assert db.get(cm.TravelParty, party_id).version == len(versions)
    return db.query(cm.PartyEvent).filter_by(party_id=party_id).order_by(cm.PartyEvent.version).all()


# ------------------------------------------------------------------- tests
def test_pg_one_student_accepts_two_proposals_at_once(pg, world):
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob", "carol")
        p_a = seed_proposal(pg, users["alice"], users["bob"], reqs["alice"], reqs["bob"], now)
        p_c = seed_proposal(pg, users["carol"], users["bob"], reqs["carol"], reqs["bob"], now)
        outcomes, details = race(pg, [accept_job(p_a, users["bob"], "k1"),
                                      accept_job(p_c, users["bob"], "k2")])

        assert sorted(outcomes, key=str) == [200, 409], (outcomes, details)
        assert details[outcomes.index(409)]["code"] in ("already_resolved", "participant_busy")
        db = pg()
        try:
            members = db.query(cm.PartyMember).filter_by(user_id=users["bob"]).all()
            assert len(members) == 1 and members[0].active
            party = db.get(cm.TravelParty, members[0].party_id)
            assert party.state == cm.PartyState.AGREED
            assert [e.event_type for e in check_event_log(db, party.id)] == ["PARTY_AGREED"]
            mine = cm.ConnectionProposal.id.in_([p_a, p_c])
            accepted = db.query(cm.ConnectionProposal).filter(mine, cm.ConnectionProposal.state == PS.ACCEPTED).all()
            expired = db.query(cm.ConnectionProposal).filter(mine, cm.ConnectionProposal.state == PS.EXPIRED).all()
            assert len(accepted) == 1 and len(expired) == 1
            assert accepted[0].party_id == party.id and expired[0].party_id is None
            win = accepted[0].proposer_request_id
            lose = expired[0].proposer_request_id
            assert db.get(cm.TravelRequest, reqs["bob"]).status == RS.RESERVED
            assert db.get(cm.TravelRequest, win).status == RS.RESERVED
            assert db.get(cm.TravelRequest, lose).status == RS.OPEN
            assert db.query(cm.PartyMember).filter_by(party_id=party.id, active=True).count() == 2
            assert db.query(cm.IdempotencyRecord).filter_by(user_id=users["bob"]).count() == 1
            assert db.query(cm.TravelParty).join(
                cm.PartyMember, cm.PartyMember.party_id == cm.TravelParty.id
            ).filter(cm.PartyMember.user_id.in_(list(users.values()))).distinct().count() == 1
        finally:
            db.close()


def test_pg_two_students_race_for_one_request(pg, world):
    """carol -> alice (alice accepts) vs alice -> dave (dave accepts)."""
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "carol", "dave")
        p_ca = seed_proposal(pg, users["carol"], users["alice"], reqs["carol"], reqs["alice"], now)
        p_ad = seed_proposal(pg, users["alice"], users["dave"], reqs["alice"], reqs["dave"], now)
        outcomes, details = race(pg, [accept_job(p_ca, users["alice"], "k1"),
                                      accept_job(p_ad, users["dave"], "k2")])
        assert sorted(outcomes, key=str) == [200, 409], (outcomes, details)
        db = pg()
        try:
            uids = list(users.values())
            assert db.query(cm.PartyMember).filter(
                cm.PartyMember.user_id.in_(uids), cm.PartyMember.active.is_(True)).count() == 2
            assert db.get(cm.TravelRequest, reqs["alice"]).status == RS.RESERVED
            loser = reqs["dave"] if outcomes[0] == 200 else reqs["carol"]
            assert db.get(cm.TravelRequest, loser).status == RS.OPEN
            assert sorted(p.state.value for p in db.query(cm.ConnectionProposal).filter(
                cm.ConnectionProposal.id.in_([p_ca, p_ad]))) == ["ACCEPTED", "EXPIRED"]
            if outcomes[1] == 409:  # dave is not in the winning party: nothing about it leaks
                assert details[1]["current"]["active_party"] is None
        finally:
            db.close()


def test_pg_both_members_cancel_simultaneously(pg, world):
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        party_id = seed_party(pg, world.ids, [users["alice"], users["bob"]],
                              [reqs["alice"], reqs["bob"]], now)
        outcomes, details = race(pg, [cancel_job(party_id, users["alice"], "ka"),
                                      cancel_job(party_id, users["bob"], "kb")])
        assert outcomes == [200, 200], (outcomes, details)
        db = pg()
        try:
            assert db.get(cm.TravelParty, party_id).state == cm.PartyState.CANCELLED
            cancelled = [e for e in check_event_log(db, party_id) if e.event_type == "PARTY_CANCELLED"]
            assert len(cancelled) == 1
            actor = cancelled[0].actor_id
            by_user = {users["alice"]: reqs["alice"], users["bob"]: reqs["bob"]}
            for uid, rid in by_user.items():
                expected = RS.CANCELLED if uid == actor else RS.OPEN
                assert db.get(cm.TravelRequest, rid).status == expected
            assert db.query(cm.PartyMember).filter_by(party_id=party_id, active=True).count() == 0
            outbox = db.query(cm.OutboxMessage).filter_by(event_id=cancelled[0].id).all()
            assert sorted(o.recipient_id for o in outbox) == sorted(users.values())
        finally:
            db.close()


@pytest.mark.parametrize("canceller", ["approver", "proposer"])
def test_pg_cancel_racing_a_change_approval(pg, world, canceller):
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        party_id = seed_party(pg, world.ids, [users["alice"], users["bob"]],
                              [reqs["alice"], reqs["bob"]], now)
        db = pg()
        change = cm.PartyChangeProposal(
            party_id=party_id, proposer_id=users["bob"],
            new_departure=campus_time.to_db(now + timedelta(minutes=60)),
            expected_party_version=1, state=cm.ChangeState.PENDING,
            created_at=campus_time.to_db(now))
        db.add(change)
        db.flush()
        campus_events.record_party_event(
            db, db.get(cm.TravelParty, party_id), users["bob"], cm.PartyEventType.CHANGE_PROPOSED,
            {"change_id": change.id}, now)
        change_id = change.id
        db.commit()
        db.close()

        who = users["alice"] if canceller == "approver" else users["bob"]
        outcomes, details = race(pg, [approve_job(party_id, change_id, users["alice"], 2),
                                      cancel_job(party_id, who, "kc")])

        assert outcomes[1] == 200, (outcomes, details)             # cancel always succeeds
        assert outcomes[0] in (200, 409), (outcomes, details)      # approve: first, or "no longer pending"
        db = pg()
        try:
            party = db.get(cm.TravelParty, party_id)
            assert party.state == cm.PartyState.CANCELLED
            events = [e.event_type for e in check_event_log(db, party_id)]
            assert events.count("PARTY_CANCELLED") == 1 and events[-1] == "PARTY_CANCELLED"
            ch = db.get(cm.PartyChangeProposal, change_id)
            if outcomes[0] == 200:
                assert ch.state == cm.ChangeState.APPROVED and "PARTY_CHANGED" in events
            else:
                assert ch.state == cm.ChangeState.SUPERSEDED and "PARTY_CHANGED" not in events
            assert db.query(cm.PartyMember).filter_by(party_id=party_id, active=True).count() == 0
        finally:
            db.close()


@pytest.mark.parametrize("patcher", ["proposer", "recipient"])
def test_pg_accept_racing_a_request_patch(pg, world, patcher):
    for _ in range(ITERATIONS):
        users, reqs, now = world("alice", "bob")
        pid = seed_proposal(pg, users["alice"], users["bob"], reqs["alice"], reqs["bob"], now)
        who = "alice" if patcher == "proposer" else "bob"
        new_latest = now + timedelta(minutes=150)
        outcomes, details = race(pg, [accept_job(pid, users["bob"], "k"),
                                      patch_request_job(reqs[who], users[who], new_latest)])

        assert all(o in (200, 409) for o in outcomes), (outcomes, details)
        assert outcomes.count(200) >= 1
        db = pg()
        try:
            req = db.get(cm.TravelRequest, reqs[who])
            proposal = db.get(cm.ConnectionProposal, pid)
            if outcomes[0] == 200:
                # accept won: the request was reserved at its original version, PATCH refused
                assert outcomes[1] == 409
                assert proposal.state == PS.ACCEPTED
                assert req.status == RS.RESERVED and req.version == 2
                members = db.query(cm.PartyMember).filter(
                    cm.PartyMember.user_id.in_(list(users.values()))).all()
                assert len(members) == 2 and all(m.active for m in members)
                assert len({m.party_id for m in members}) == 1
            else:
                # PATCH won: the proposal died with the old request version, no party exists
                assert outcomes[1] == 200
                assert proposal.state == PS.EXPIRED
                assert req.status == RS.OPEN and req.version == 2
                assert db.query(cm.PartyMember).filter(
                    cm.PartyMember.user_id.in_(list(users.values()))).count() == 0
                assert db.get(cm.TravelRequest, reqs["bob" if who == "alice" else "alice"]).status == RS.OPEN
        finally:
            db.close()


def test_pg_cross_accepts_with_two_requests_per_student_never_deadlock(pg, world):
    """X and Y each have two requests. P1: X -> Y (x1, y1) and P2: Y -> X (y2, x2).
    Y accepts P1 while X accepts P2: the request lock sets are disjoint, so only the
    user-row locks / ascending member insertion keep the unique-index waits from
    forming a cycle. Exactly one accept wins, the other is a clean 409, never a 500."""
    for _ in range(ITERATIONS):
        users, reqs, now = world("xavier", "yara")
        x1, y1 = reqs["xavier"], reqs["yara"]
        x2 = seed_request(pg, world.ids, users["xavier"], now, start_min=200, end_min=300)
        y2 = seed_request(pg, world.ids, users["yara"], now, start_min=200, end_min=300)
        p1 = seed_proposal(pg, users["xavier"], users["yara"], x1, y1, now)
        p2 = seed_proposal(pg, users["yara"], users["xavier"], y2, x2, now)
        outcomes, details = race(pg, [accept_job(p1, users["yara"], "k1"),
                                      accept_job(p2, users["xavier"], "k2")])

        assert sorted(outcomes, key=str) == [200, 409], (outcomes, details)
        assert details[outcomes.index(409)]["code"] in ("participant_busy", "already_resolved")
        db = pg()
        try:
            members = db.query(cm.PartyMember).filter(
                cm.PartyMember.user_id.in_(list(users.values()))).all()
            assert len(members) == 2 and all(m.active for m in members)
            assert len({m.party_id for m in members}) == 1
            states = sorted(p.state.value for p in db.query(cm.ConnectionProposal).filter(
                cm.ConnectionProposal.id.in_([p1, p2])))
            assert states == ["ACCEPTED", "PENDING"]  # the loser's proposal stays PENDING
            winner_reqs = {m.request_id for m in members}
            for rid in (x1, y1, x2, y2):
                expected = RS.RESERVED if rid in winner_reqs else RS.OPEN
                assert db.get(cm.TravelRequest, rid).status == expected
            assert [e.event_type for e in check_event_log(db, members[0].party_id)] == ["PARTY_AGREED"]
        finally:
            db.close()
