"""Shared builders for the campus connection/party tests (fictional data only).

Two layers:
- plain ORM seeding functions that take a session factory (used by the threaded
  SQLite race tests and the opt-in Postgres tests), and
- a ``world`` fixture that drives the HTTP API through the shared TestClient.
"""

import asyncio
import threading
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import campus_time
from app.models import campus_model as cm
from app.models import profile_model, user_model

API = "/api/campus"


# --------------------------------------------------------------------------
# plain ORM seeding (session-factory based)
# --------------------------------------------------------------------------
def seed_college(sf, tag="t"):
    """College + three landmarks. Returns ids."""
    db = sf()
    try:
        college = user_model.College(name=f"College {tag}")
        db.add(college)
        db.flush()
        rows = {
            "campus": cm.CampusLandmark(
                college_id=college.id, name="Main Gate", kind=cm.LandmarkKind.CAMPUS_POINT,
                latitude=19.1, longitude=72.84, timezone="Asia/Kolkata", active=True),
            "hub": cm.CampusLandmark(
                college_id=college.id, name="Airport Terminal", kind=cm.LandmarkKind.HUB,
                latitude=19.09, longitude=72.87, timezone="Asia/Kolkata", active=True),
            "campus2": cm.CampusLandmark(
                college_id=college.id, name="Library", kind=cm.LandmarkKind.CAMPUS_POINT,
                latitude=19.101, longitude=72.841, timezone="Asia/Kolkata", active=True),
        }
        db.add_all(rows.values())
        db.flush()
        out = {"college_id": college.id, **{k: v.id for k, v in rows.items()}}
        db.commit()
        return out
    finally:
        db.close()


def seed_user(sf, college_id, key, tag="t", phone=None):
    db = sf()
    try:
        user = user_model.User(
            email=f"{key}.{tag}@example.test", full_name=f"{key.title()} Example",
            hashed_password="not-a-real-hash", college_id=college_id,
        )
        db.add(user)
        db.flush()
        if phone:
            db.add(profile_model.Profile(user_id=user.id, phone_number=phone))
        uid = user.id
        db.commit()
        return uid
    finally:
        db.close()


def seed_request(sf, ids, user_id, now, start_min=10, end_min=120, direction="TO_HUB",
                 status="OPEN", flexibility=False):
    db = sf()
    try:
        row = cm.TravelRequest(
            user_id=user_id, college_id=ids["college_id"],
            mode=cm.TravelMode.SHARED_TAXI_PARTY,
            origin_landmark_id=ids["campus"], hub_id=ids["hub"],
            direction=cm.Direction(direction),
            earliest_departure=campus_time.to_db(now + timedelta(minutes=start_min)),
            latest_departure=campus_time.to_db(now + timedelta(minutes=end_min)),
            timezone="Asia/Kolkata", flexibility_consent=flexibility,
            expires_at=campus_time.to_db(now + timedelta(minutes=end_min)),
            status=cm.TravelRequestStatus(status), version=1,
            created_at=campus_time.to_db(now), updated_at=campus_time.to_db(now),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def seed_proposal(sf, proposer_id, recipient_id, req_p, req_r, now, ttl_min=30, suggestion_id=None):
    """A PENDING proposal between two OPEN requests (versions recorded as they are)."""
    db = sf()
    try:
        rp, rr = db.get(cm.TravelRequest, req_p), db.get(cm.TravelRequest, req_r)
        row = cm.ConnectionProposal(
            suggestion_id=suggestion_id, proposer_id=proposer_id, recipient_id=recipient_id,
            proposer_request_id=req_p, recipient_request_id=req_r,
            proposer_request_version=rp.version, recipient_request_version=rr.version,
            state=cm.ProposalState.PENDING,
            expires_at=campus_time.to_db(now + timedelta(minutes=ttl_min)),
            version=1, created_at=campus_time.to_db(now),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def seed_party(sf, ids, users, reqs, now, departure_min=10):
    """An AGREED party for two (user, request) pairs without going through accept.
    Returns party_id. The party starts at version 1 (one PARTY_AGREED event)."""
    from app.services.campus_events import record_party_event

    db = sf()
    try:
        party = cm.TravelParty(
            state=cm.PartyState.AGREED,
            agreed_departure=campus_time.to_db(now + timedelta(minutes=departure_min)),
            meeting_landmark_id=ids["campus"], hub_id=ids["hub"],
            direction=cm.Direction.TO_HUB, timezone="Asia/Kolkata",
            transport_responsibility="x", version=0, created_at=campus_time.to_db(now),
        )
        db.add(party)
        db.flush()
        for uid, rid in zip(users, reqs):
            db.add(cm.PartyMember(party_id=party.id, user_id=uid, request_id=rid, active=True))
            db.get(cm.TravelRequest, rid).status = cm.TravelRequestStatus.RESERVED
        db.flush()
        record_party_event(db, party, users[0], cm.PartyEventType.PARTY_AGREED, {}, now)
        pid = party.id
        db.commit()
        return pid
    finally:
        db.close()


# --------------------------------------------------------------------------
# threaded racing (SQLite file DB and Postgres)
# --------------------------------------------------------------------------
def race(session_factory, jobs, timeout=120):
    """Run each ``job(db) -> coroutine`` in its own thread with its own Session,
    released together by a Barrier. Outcome per job: 200 (or the stored Result),
    an HTTPException's status code, or "ERROR: ..." for anything else."""
    barrier = threading.Barrier(len(jobs))
    outcomes = [None] * len(jobs)
    details = [None] * len(jobs)

    def worker(index, job):
        db = session_factory()
        try:
            coro = job(db)  # load users etc. before the starting gun
            db.rollback()  # hold no transaction/lock while waiting at the barrier
            barrier.wait(timeout=60)
            asyncio.run(coro)
            outcomes[index] = 200
        except HTTPException as exc:
            outcomes[index] = exc.status_code
            details[index] = exc.detail
        except Exception as exc:  # noqa: BLE001
            outcomes[index] = f"ERROR: {type(exc).__name__}: {str(exc)[:200]}"
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
        assert not t.is_alive(), "worker hung (deadlock?)"
    return outcomes, details


# --------------------------------------------------------------------------
# HTTP-level world
# --------------------------------------------------------------------------
@pytest.fixture
def world(client, clock, college, landmarks, make_user, make_travel_request, test_session_factory):
    users, headers = {}, {}
    for key, phone in (("alice", "+910000000001"), ("bob", "+910000000002"),
                       ("carol", "+910000000003"), ("dave", "+910000000004")):
        user, hdr = make_user(f"{key}@example.test", f"{key.title()} Example", college, phone)
        users[key], headers[key] = user, hdr

    w = SimpleNamespace(client=client, clock=clock, users=users, headers=headers,
                        landmarks=landmarks, college=college, sf=test_session_factory)

    def new_request(who, start=10, end=120, **kw):
        return make_travel_request(users[who], landmarks, start_offset_min=start,
                                   end_offset_min=end, **kw)

    def suggestion(req_a, req_b, warnings=()):
        low, high = sorted((req_a.id, req_b.id))
        db = test_session_factory()
        try:
            now = campus_time.to_db(clock.now)
            row = cm.PairSuggestion(
                request_low_id=low, request_high_id=high, rule_version="window-overlap-v1",
                reason=cm.SuggestionReason.WINDOW_OVERLAP, feasible_start=now, feasible_end=now,
                estimate_status=cm.EstimateStatus.UNVERIFIED, estimate_failure="timeout",
                warnings=list(warnings), valid_until=campus_time.to_db(clock.now + timedelta(minutes=15)),
                created_at=now,
            )
            db.add(row)
            db.commit()
            return row.id
        finally:
            db.close()

    def propose(by, sugg_id, ack=False):
        return client.post(f"{API}/suggestions/{sugg_id}/connections", headers=headers[by],
                           json={"acknowledge_warnings": ack})

    def pair(a="alice", b="bob", warnings=(), start=10, end=120):
        """Two OPEN requests, a suggestion and a PENDING proposal a -> b."""
        ra, rb = new_request(a, start, end), new_request(b, start, end)
        sid = suggestion(ra, rb, warnings)
        resp = propose(a, sid, ack=bool(warnings))
        assert resp.status_code == 201, resp.text
        return SimpleNamespace(proposal=resp.json(), ra=ra, rb=rb, suggestion_id=sid)

    def accept(by, pid, version=None, key="k1"):
        if version is None:
            version = client.get(f"{API}/connections", headers=headers[by]).json()
            version = next(p["version"] for p in version if p["id"] == pid)
        return client.post(f"{API}/connections/{pid}/accept", headers=headers[by],
                           json={"expected_version": version, "idempotency_key": key})

    def party(a="alice", b="bob", **kw):
        """An AGREED party created through the real propose + accept flow."""
        p = pair(a, b, **kw)
        resp = accept(b, p.proposal["id"], p.proposal["version"], key=f"setup-{a}-{b}")
        assert resp.status_code == 200, resp.text
        return SimpleNamespace(id=resp.json()["party"]["id"], ra=p.ra, rb=p.rb,
                               proposal_id=p.proposal["id"], body=resp.json())

    def rows(model, **filters):
        db = test_session_factory()
        try:
            return db.query(model).filter_by(**filters).all()
        finally:
            db.close()

    def get(model, ident):
        db = test_session_factory()
        try:
            row = db.get(model, ident)
            if row is not None:
                db.refresh(row)
            return row
        finally:
            db.close()

    def events(party_id, event_type=None):
        out = rows(cm.PartyEvent, party_id=party_id)
        return [e for e in out if event_type is None or e.event_type == event_type]

    for name, fn in dict(new_request=new_request, suggestion=suggestion, propose=propose, pair=pair,
                         accept=accept, party=party, rows=rows, get=get, events=events).items():
        setattr(w, name, fn)
    return w
