"""Consolidated ACCEPTANCE suite for campus scheduling (shared-taxi parties).

One section per campus scheduling acceptance case listed in docs/campus-scheduling.md. Everything goes
through the public HTTP / WebSocket API with real JWT headers; the only direct
database writes are the users, the college and the landmarks. Database reads are
used for assertions only (exactly one party / one event / outbox status).

Fakes: a settable clock (``clock``), a fake routing provider (``provider``,
patched into ``campus_estimates.map_service.get_route_from_ola``) and a recording
socket layer (``ws_delivery``). No network. Fictional data only.

Set TRIPSYNC_E2E_TRANSCRIPT=<path> to have ``test_full_happy_path_with_two_devices``
write a sanitized, deterministic Markdown transcript of its real HTTP traffic;
TRIPSYNC_E2E_RECONCILE_TRANSCRIPT=<path> does the same for the recovery scenarios.
"""

import asyncio
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core import campus_rules, campus_time
from app.db.database import Base, get_db
from app.main import app
from app.models import campus_model as cm
from app.services import auth_service, campus_estimates, campus_outbox, map_service, message_service
from tests.campus_clients import API, PendingCancel, SimulatedDevice, Transcript
from tests.campus_party_helpers import race, seed_college, seed_user
from tests.test_campus_party_postgres import pg  # noqa: F401  (fixture only)

FORBIDDEN_CHAT = "Chat is only available with an approved ride partner"
PG_URL = os.environ.get("TRIPSYNC_TEST_PG_URL")


# ==========================================================================
# fakes and fixtures
# ==========================================================================
class FakeProvider:
    """Replaces map_service.get_route_from_ola (no network)."""

    def __init__(self):
        self.calls = 0
        self.mode = "ok"
        self.duration = 1800
        self.distance = 12000

    async def __call__(self, start_lat, start_lng, end_lat, end_lng):
        self.calls += 1
        if self.mode == "ok":
            return {"polyline": [], "distance_meters": self.distance,
                    "duration_seconds": self.duration, "is_fallback": False}
        if self.mode == "timeout":
            raise map_service.RoutingProviderTimeout("Routing provider timed out")
        if self.mode == "error":
            raise map_service.RoutingProviderError("Routing provider unavailable")
        raise AssertionError(self.mode)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", fake)
    return fake


@pytest.fixture(autouse=True)
def _chat_stamps_use_fake_clock(monkeypatch, clock):
    """Chat messages are stamped with datetime.utcnow(); route that to the fake clock
    so nothing real-time can leak into assertions or the transcript."""

    class _ClockDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return campus_time.to_db(clock.now)

    monkeypatch.setattr(message_service, "datetime", _ClockDatetime)


class World:
    """Named students, each with a SimulatedDevice, over the shared TestClient."""

    def __init__(self, client, clock, college, landmarks, make_user, sf):
        self.client, self.clock, self.college = client, clock, college
        self.landmarks, self._make_user, self.sf = landmarks, make_user, sf
        self.transcript = None
        self.devices, self.users, self.phones = {}, {}, {}

    def record(self, transcript):
        self.transcript = transcript
        for dev in self.devices.values():
            dev.transcript = transcript

    def device(self, name):
        if name not in self.devices:
            phone = f"+9100000000{len(self.devices) + 1:02d}"
            user, headers = self._make_user(
                f"{name}@example.test", f"{name.title()} Example", self.college, phone)
            self.users[name], self.phones[name] = user, phone
            self.devices[name] = SimulatedDevice(
                name, self.client, headers, user.id, self.transcript)
        return self.devices[name]

    def uid(self, name):
        self.device(name)
        return self.users[name].id

    def headers(self, name):
        return self.device(name).headers

    def email(self, name):
        return f"{name}@example.test"

    def iso(self, minutes):
        return (self.clock.now + timedelta(minutes=minutes)).isoformat()

    def request_body(self, start, end, direction="TO_HUB", hub_id=None, arrive_by=None,
                     flex=False):
        body = {
            "origin_landmark_id": self.landmarks["campus"].id,
            "hub_id": hub_id or self.landmarks["hub"].id,
            "direction": direction,
            "earliest_departure": self.iso(start),
            "latest_departure": self.iso(end),
            "timezone": "Asia/Kolkata",
            "flexibility_consent": flex,
        }
        if arrive_by is not None:
            body["arrive_by"] = self.iso(arrive_by)
        return body

    def new_request(self, name, start, end, **kw):
        resp = self.device(name).create_request(self.request_body(start, end, **kw))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def suggestions(self, name, request_id):
        resp = self.device(name).search(request_id)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def suggestion_for(self, name, request_id, other):
        found = [s for s in self.suggestions(name, request_id)["suggestions"]
                 if s["other"]["user_id"] == self.uid(other)]
        assert len(found) == 1, found
        return found[0]

    def agree(self, a, b, start=10, end=120):
        """Real flow: both post requests, a searches and proposes, b accepts."""
        ra, rb = self.new_request(a, start, end), self.new_request(b, start, end)
        sugg = self.suggestion_for(a, ra["id"], b)
        conn = self.device(a).propose(sugg["id"])
        assert conn.status_code == 201, conn.text
        conn = conn.json()
        acc = self.device(b).accept(conn["id"], conn["version"])
        assert acc.status_code == 200, acc.text
        party = acc.json()["party"]
        return SimpleNamespace(party_id=party["id"], ra=ra, rb=rb, connection=conn,
                               party=party, a=a, b=b)

    def add_hub(self, name="Central Station"):
        db = self.sf()
        try:
            row = cm.CampusLandmark(
                college_id=self.college.id, name=name, kind=cm.LandmarkKind.HUB,
                latitude=19.0, longitude=72.9, timezone="Asia/Kolkata", active=True)
            db.add(row)
            db.commit()
            return row.id
        finally:
            db.close()

    def rows(self, model, **filters):
        return db_rows(self.sf, model, **filters)

    def events_of(self, party_id):
        return [(e.version, e.event_type) for e in
                sorted(self.rows(cm.PartyEvent, party_id=party_id), key=lambda e: e.version)]

    def outbox_for(self, party_id, event_type):
        db = self.sf()
        try:
            ids = [e.id for e in db.query(cm.PartyEvent).filter_by(
                party_id=party_id, event_type=event_type).all()]
            rows = db.query(cm.OutboxMessage).filter(
                cm.OutboxMessage.event_id.in_(ids or [-1])).order_by(cm.OutboxMessage.id).all()
            return [(r.recipient_id, getattr(r.status, "value", r.status), r.attempts,
                     r.last_error) for r in rows]
        finally:
            db.close()

    def dispatch_pending(self):
        async def run():
            db = self.sf()
            try:
                return await campus_outbox.dispatch_pending(db)
            finally:
                db.close()
        return asyncio.run(run())


def db_rows(sf, model, **filters):
    db = sf()
    try:
        return db.query(model).filter_by(**filters).all()
    finally:
        db.close()


@pytest.fixture
def world(client, clock, college, landmarks, make_user, test_session_factory, provider):
    return World(client, clock, college, landmarks, make_user, test_session_factory)


def other_request_ids(body):
    return [s["other_request"]["id"] for s in body["suggestions"]]


def code_of(resp):
    return resp.json()["detail"]["code"]


def assert_no_contact(text, world, *names):
    for name in names:
        assert world.email(name) not in text and world.phones[name] not in text


# ==========================================================================
# (a) future trips posted an hour apart stay eligible; control: hours apart
# ==========================================================================
def test_compatible_future_trips_posted_an_hour_apart_remain_eligible(world, clock):
    a = world.new_request("alice", 120, 180)                  # 06:00-07:00Z
    assert (a["status"], a["version"]) == ("OPEN", 1)
    assert a["earliest_departure"]["utc"] == "2026-03-01T06:00:00Z"
    clock.advance(minutes=60)                                 # 05:00Z
    b = world.new_request("bob", 90, 150)                     # 06:30-07:30Z, created an hour later
    assert b["created_at"]["utc"] == "2026-03-01T05:00:00Z"

    alice_view = world.suggestions("alice", a["id"])
    bob_view = world.suggestions("bob", b["id"])
    assert alice_view["estimate_status"] == "VERIFIED"
    assert other_request_ids(alice_view) == [b["id"]]
    assert other_request_ids(bob_view) == [a["id"]]
    s = alice_view["suggestions"][0]
    assert s["id"] == bob_view["suggestions"][0]["id"]        # one shared suggestion row
    assert s["reason"] == "WINDOW_OVERLAP" and s["warnings"] == [] and s["proposal"] is None
    assert s["other"] == {"user_id": world.uid("bob"), "full_name": "Bob Example"}
    assert s["feasible_window"]["start"]["utc"] == "2026-03-01T06:30:00Z"
    assert s["feasible_window"]["end"]["utc"] == "2026-03-01T07:00:00Z"
    assert s["estimate"]["status"] == "VERIFIED" and s["estimate"]["duration_s"] == 1800
    assert_no_contact(str(alice_view) + str(bob_view), world, "alice", "bob")

    # creation age is irrelevant: half an hour later alice's request is 90 minutes old
    clock.advance(minutes=30)
    assert other_request_ids(world.suggestions("alice", a["id"])) == [b["id"]]
    assert other_request_ids(world.suggestions("bob", b["id"])) == [a["id"]]

    # control: same endpoints, same direction, created together, departures hours apart
    c = world.new_request("carol", 330, 390)                  # 11:00-12:00Z
    d = world.new_request("dave", 570, 630)                   # 15:00-16:00Z
    assert world.suggestions("carol", c["id"])["suggestions"] == []
    assert world.suggestions("dave", d["id"])["suggestions"] == []
    assert other_request_ids(world.suggestions("alice", a["id"])) == [b["id"]]

    # suggestions never reserve anything
    for name, req in (("alice", a), ("bob", b), ("carol", c), ("dave", d)):
        got = world.device(name).get(f"/requests/{req['id']}")
        assert got.status_code == 200 and got.json()["status"] == "OPEN"


# ==========================================================================
# (b) opposite direction / disjoint windows / other hub / mutual flexibility
# ==========================================================================
def test_opposite_direction_or_disjoint_windows_yield_no_suggestion(world):
    other_hub = world.add_hub()
    a = world.new_request("alice", 120, 180)                  # 06:00-07:00Z TO_HUB
    b = world.new_request("bob", 120, 180, direction="FROM_HUB")
    c = world.new_request("carol", 210, 270)                  # 30 minutes after alice, no consent
    d = world.new_request("dave", 120, 180, hub_id=other_hub)
    e = world.new_request("erin", 210, 270, flex=True)        # consents, alice does not
    f = world.new_request("frank", 241, 300, flex=True)       # gap of 61 minutes

    assert world.suggestions("alice", a["id"])["suggestions"] == []       # nobody qualifies
    assert world.suggestions("bob", b["id"])["suggestions"] == []         # opposite direction
    assert world.suggestions("dave", d["id"])["suggestions"] == []        # different hub
    assert a["id"] not in other_request_ids(world.suggestions("erin", e["id"]))  # one-sided consent
    assert a["id"] not in other_request_ids(world.suggestions("carol", c["id"]))

    # alice now consents too: mutual flexibility bridges a gap of up to 2 * FLEX_MINUTES
    patched = world.device("alice").call(
        "PATCH", f"/requests/{a['id']}", {"expected_version": 1, "flexibility_consent": True})
    assert patched.status_code == 200
    assert patched.json()["version"] == 2 and patched.json()["flexibility_consent"] is True

    view = world.suggestions("alice", a["id"])
    assert other_request_ids(view) == [e["id"]]               # not carol (no consent), not frank
    s = view["suggestions"][0]
    assert s["reason"] == "FLEXIBLE_WINDOW"
    assert s["feasible_window"]["start"]["utc"] == "2026-03-01T07:00:00Z"
    assert s["feasible_window"]["end"]["utc"] == "2026-03-01T07:30:00Z"
    assert campus_rules.FLEX_MINUTES == 30
    erin_view = {x["other_request"]["id"]: x for x in
                 world.suggestions("erin", e["id"])["suggestions"]}
    assert erin_view[a["id"]]["reason"] == "FLEXIBLE_WINDOW"
    assert f["id"] not in other_request_ids(view)
    assert world.suggestions("bob", b["id"])["suggestions"] == []


# ==========================================================================
# (c) simultaneous approvals involving one student -> exactly one party
# ==========================================================================
_phone_counter = count(1)


def _cast(sf, tag, names):
    ids = seed_college(sf, tag)
    cast = SimpleNamespace(ids=ids, dev={}, uid={}, email={}, phone={}, req={})
    for name in names:
        phone = f"+9199{next(_phone_counter):08d}"
        uid = seed_user(sf, ids["college_id"], name, tag, phone=phone)
        email = f"{name}.{tag}@example.test"
        headers = {"Authorization": "Bearer " + auth_service.create_access_token(
            data={"sub": email})}
        cast.uid[name], cast.email[name], cast.phone[name] = uid, email, phone
        cast.dev[name] = SimulatedDevice(name, TestClient(app), headers, uid)
    return cast


def _post_request(cast, name, clock):
    now = clock.now
    body = {
        "origin_landmark_id": cast.ids["campus"], "hub_id": cast.ids["hub"],
        "direction": "TO_HUB", "timezone": "Asia/Kolkata",
        "earliest_departure": (now + timedelta(minutes=10)).isoformat(),
        "latest_departure": (now + timedelta(minutes=120)).isoformat(),
    }
    resp = cast.dev[name].create_request(body)
    assert resp.status_code == 201, resp.text
    cast.req[name] = resp.json()["id"]


def _propose(cast, proposer, recipient):
    s = [x for x in cast.dev[proposer].search(cast.req[proposer]).json()["suggestions"]
         if x["other"]["user_id"] == cast.uid[recipient]]
    assert len(s) == 1
    resp = cast.dev[proposer].propose(s[0]["id"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _race_accepts(sf, cast, jobs):
    """jobs: [(accepting student, proposal)] released together by race()'s Barrier."""
    results = {}

    def make_job(student, proposal):
        def job(_db):
            async def go():
                dev = SimulatedDevice(student, TestClient(app), cast.dev[student].headers,
                                      cast.uid[student])
                results[proposal["id"]] = (student, dev.accept(
                    proposal["id"], proposal["version"], key=f"{student}-key-{proposal['id']}"))
            return go()
        return job

    outcomes, details = race(sf, [make_job(s, p) for s, p in jobs])
    assert outcomes == [200] * len(jobs), (outcomes, details)    # transport-level only
    return results


def _assert_loser_sees_only_own_state(cast, loser, lost_proposal, resp):
    detail = resp.json()["detail"]
    assert set(detail) == {"code", "message", "current"}
    assert detail["code"] in ("already_resolved", "participant_busy")
    assert set(detail["current"]) == {"proposal", "active_party"}
    assert detail["current"]["proposal"]["id"] == lost_proposal["id"]
    assert detail["current"]["proposal"]["party_id"] is None        # nobody's party hangs off it
    mine = cast.dev[loser].get("/parties/active").json()["party"]
    own = detail["current"]["active_party"]
    assert (own is None) == (mine is None)
    partner = None
    if own is not None:                       # only the loser's OWN party, never a stranger's
        assert own["id"] == mine["id"]
        assert [m["user_id"] for m in own["members"] if m["you"]] == [cast.uid[loser]]
        partner = own["partner"]["user_id"]
    for name in cast.uid:
        if name == loser or cast.uid[name] == partner:
            continue
        assert cast.email[name] not in resp.text and cast.phone[name] not in resp.text, name


def _scoped(sf, cast):
    """Rows belonging to this cast only (the Postgres schema is shared by iterations)."""
    uids = set(cast.uid.values())
    db = sf()
    try:
        members = db.query(cm.PartyMember).filter(cm.PartyMember.user_id.in_(uids)).all()
        pids = {m.party_id for m in members}
        return SimpleNamespace(
            parties=db.query(cm.TravelParty).filter(cm.TravelParty.id.in_(pids or [-1])).all(),
            events=db.query(cm.PartyEvent).filter(cm.PartyEvent.party_id.in_(pids or [-1])).all(),
            active=[m for m in members if m.active],
            proposals=db.query(cm.ConnectionProposal).filter(
                cm.ConnectionProposal.proposer_id.in_(uids)).all(),
            requests=db.query(cm.TravelRequest).filter(cm.TravelRequest.user_id.in_(uids)).all(),
        )
    finally:
        db.close()


def _one_student_accepts_two_proposals(sf, clock, tag):
    cast = _cast(sf, tag, ("alice", "bob", "carol", "dave"))
    for name in cast.dev:
        _post_request(cast, name, clock)
    prop = {p: _propose(cast, p, "bob") for p in ("alice", "carol")}
    results = _race_accepts(sf, cast, [("bob", prop["alice"]), ("bob", prop["carol"])])

    statuses = sorted(r.status_code for _, r in results.values())
    assert statuses == [200, 409], statuses
    won = next(p for p in prop if results[prop[p]["id"]][1].status_code == 200)
    lost = next(p for p in prop if p != won)
    loser_resp = results[prop[lost]["id"]][1]
    _assert_loser_sees_only_own_state(cast, "bob", prop[lost], loser_resp)

    # exactly one party and one PARTY_AGREED event in the database
    rows = _scoped(sf, cast)
    assert len(rows.parties) == 1
    assert [e.event_type for e in rows.events] == ["PARTY_AGREED"]
    assert len(rows.active) == 2

    # the loser can fetch fresh state immediately and sees the proposal EXPIRED
    bob = cast.dev["bob"]
    expired = bob.get("/connections?state=EXPIRED").json()
    accepted = bob.get("/connections?state=ACCEPTED").json()
    assert [p["id"] for p in expired] == [prop[lost]["id"]]
    assert [p["id"] for p in accepted] == [prop[won]["id"]]
    party = bob.get("/parties/active").json()["party"]
    assert party["id"] == accepted[0]["party_id"]

    # requests are consistent: one RESERVED pair, the other still OPEN
    status = lambda who, req: cast.dev[who].get(f"/requests/{req}").json()["status"]  # noqa: E731
    assert status(won, cast.req[won]) == "RESERVED" and status("bob", cast.req["bob"]) == "RESERVED"
    assert status(lost, cast.req[lost]) == "OPEN"

    # the loser's proposer cannot see the winning party at all
    assert cast.dev[lost].get(f"/parties/{party['id']}").status_code == 404
    assert cast.dev[lost].get("/parties/active").json()["party"] is None

    # a third student still finds the OPEN request, and only that one
    third = cast.dev["dave"].search(cast.req["dave"]).json()["suggestions"]
    assert [s["other_request"]["id"] for s in third] == [cast.req[lost]]


def _two_students_compete_for_one(sf, clock, tag):
    """carol -> alice (alice accepts) races alice -> dave (dave accepts)."""
    cast = _cast(sf, tag, ("alice", "carol", "dave"))
    for name in cast.dev:
        _post_request(cast, name, clock)
    p_ca = _propose(cast, "carol", "alice")
    p_ad = _propose(cast, "alice", "dave")
    results = _race_accepts(sf, cast, [("alice", p_ca), ("dave", p_ad)])

    statuses = sorted(r.status_code for _, r in results.values())
    assert statuses == [200, 409], statuses
    loser_student, loser_resp = next(v for v in results.values() if v[1].status_code == 409)
    lost = p_ca if loser_student == "alice" else p_ad
    _assert_loser_sees_only_own_state(cast, loser_student, lost, loser_resp)

    rows = _scoped(sf, cast)
    assert len(rows.parties) == 1
    assert [e.event_type for e in rows.events] == ["PARTY_AGREED"]
    states = sorted(p.state.value for p in rows.proposals)
    assert states == ["ACCEPTED", "EXPIRED"]
    reserved = [r for r in rows.requests if r.status.value == "RESERVED"]
    opened = [r for r in rows.requests if r.status.value == "OPEN"]
    assert len(reserved) == 2 and len(opened) == 1
    assert cast.dev[loser_student].get("/connections?state=EXPIRED").status_code == 200


@contextmanager
def _serve_from(sf):
    """Point the app's get_db dependency at ``sf`` (restores the previous override)."""
    previous = app.dependency_overrides.get(get_db)

    def _override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def _file_sqlite(path, mode):
    engine = create_engine(f"sqlite:///{path}",
                           connect_args={"check_same_thread": False, "timeout": 30})
    if mode == "begin_immediate":      # emulates the serialisation of SELECT ... FOR UPDATE
        @event.listens_for(engine, "connect")
        def _no_driver_begin(dbapi_connection, _):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def _begin_immediate(conn):
            conn.exec_driver_sql("BEGIN IMMEDIATE")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.mark.parametrize("mode", ["plain", "begin_immediate"])
def test_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party(
        mode, tmp_path, clock, provider, ws_delivery):
    for i in range(3):                                       # fresh database and data each time
        engine = _file_sqlite(tmp_path / f"race{i}.db", mode)
        sf = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        try:
            with _serve_from(sf):
                _one_student_accepts_two_proposals(sf, clock, f"s{i}")
        finally:
            engine.dispose()
    for i in range(3):
        engine = _file_sqlite(tmp_path / f"race2_{i}.db", mode)
        sf = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        try:
            with _serve_from(sf):
                _two_students_compete_for_one(sf, clock, f"c{i}")
        finally:
            engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="set TRIPSYNC_TEST_PG_URL to run the Postgres variant")
def test_postgres_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party(
        pg, clock, provider, ws_delivery):
    iterations = int(os.environ.get("TRIPSYNC_TEST_PG_ITERATIONS", "10"))
    with _serve_from(pg):
        for i in range(iterations):
            _one_student_accepts_two_proposals(pg, clock, f"pa{i}")
            _two_students_compete_for_one(pg, clock, f"pb{i}")


# ==========================================================================
# (d) cancel while pushes fail and the reply is lost; both phones converge
# ==========================================================================
def test_cancel_offline_then_both_devices_converge_after_restart(world, clock, ws_delivery):
    p = world.agree("alice", "bob")
    pid = p.party_id
    alice, bob = world.device("alice"), world.device("bob")
    alice.reconcile()
    bob.reconcile()
    assert (alice.cache.version, alice.cache.state) == (1, "AGREED")
    assert (bob.cache.version, bob.cache.state) == (1, "AGREED")
    pushed_before = len(ws_delivery.sent)

    ws_delivery.fail_all()                                    # no socket accepts anything
    assert alice.cancel(pid, drop_response=True) is None      # server committed, reply lost
    key = alice.pending_cancel.key

    # alice shows "pending", the server holds exactly one PARTY_CANCELLED event
    assert alice.shows == "CANCEL_PENDING" and alice.cache.state == "AGREED"
    assert world.events_of(pid) == [(1, "PARTY_AGREED"), (2, "PARTY_CANCELLED")]
    # pushes failed but the outbox rows are PENDING (retained), not lost
    rows = world.outbox_for(pid, "PARTY_CANCELLED")
    assert sorted(r[0] for r in rows) == sorted([world.uid("alice"), world.uid("bob")])
    assert {r[1] for r in rows} == {"PENDING"} and {r[2] for r in rows} == {1}
    assert {r[3] for r in rows} == {"no_live_socket"}
    assert len(ws_delivery.sent) == pushed_before             # nothing was delivered
    assert len([m for _, m in ws_delivery.attempts
                if m.get("event_type") == "PARTY_CANCELLED"]) == 2
    # bob's phone never heard: still AGREED locally
    assert bob.shows == "AGREED" and bob.cache.version == 1

    # both phones restart: caches are gone, alice's journal is not
    alice.restart()
    bob.restart()
    assert alice.cache.state is None and bob.cache.state is None
    assert alice.shows == "CANCEL_PENDING" and alice.pending_cancel.key == key

    # REST alone brings them to the same server version and state
    alice.reconcile()
    bob.reconcile()
    server = alice.get(f"/parties/{pid}").json()
    assert server["version"] == 2 and server["state"] == "CANCELLED"
    for dev in (alice, bob):
        assert (dev.cache.party_id, dev.cache.version, dev.cache.state) == (pid, 2, "CANCELLED")
        assert dev.cache.event_types == ["PARTY_AGREED", "PARTY_CANCELLED"]
    assert alice.pending_cancel is None                       # resolved only now, by the server
    assert alice.cancel_resolution == "confirmed_by_server_CANCELLED"
    assert alice.shows == "CANCELLED"

    # the retry with the SAME key returns the stored result; no second event
    alice.pending_cancel = PendingCancel(pid, key)            # the phone had not seen the reply
    retry = alice.retry_cancel()
    assert retry.status_code == 200 and retry.headers["Idempotent-Replay"] == "true"
    assert retry.json()["state"] == "CANCELLED" and retry.json()["version"] == 2
    assert retry.json()["partner"]["phone_number"] is None
    other = bob.post(f"/parties/{pid}/cancel", {"idempotency_key": "bob-other-key"})
    assert other.status_code == 200 and other.json()["version"] == 2   # already cancelled: no-op
    assert world.events_of(pid) == [(1, "PARTY_AGREED"), (2, "PARTY_CANCELLED")]
    reuse = alice.post(f"/parties/{pid + 1000}/cancel", {"idempotency_key": key})
    assert reuse.status_code in (404, 422)

    # the fetch acknowledged the outbox rows, so restoring delivery re-pushes nothing
    assert {r[1] for r in world.outbox_for(pid, "PARTY_CANCELLED")} == {"ACKED"}
    ws_delivery.restore()
    clock.advance(minutes=1)
    assert world.dispatch_pending() == 0
    assert not [m for _, m in ws_delivery.sent if m.get("event_type") == "PARTY_CANCELLED"]

    # contact details are gone after the end; names stay
    for dev in (alice, bob):
        ended = dev.get("/parties/active").json()
        assert ended["party"] is None and ended["recently_ended"]["state"] == "CANCELLED"
        partner = ended["recently_ended"]["partner"]
        assert partner["phone_number"] is None and partner["email"] is None
        assert partner["full_name"]
        assert "+91" not in str(ended) and "@example.test" not in str(ended)

    # alice cancelled -> her request is CANCELLED; bob's window is still valid -> OPEN again
    assert alice.get(f"/requests/{p.ra['id']}").json()["status"] == "CANCELLED"
    reopened = bob.get(f"/requests/{p.rb['id']}").json()
    assert reopened["status"] == "OPEN" and reopened["version"] == 3
    assert bob.search(p.rb["id"]).status_code == 200


def test_failed_push_is_retried_later_and_marked_sent(world, clock, ws_delivery):
    p = world.agree("alice", "bob")
    alice, bob = world.device("alice"), world.device("bob")
    alice.reconcile()
    bob.reconcile()

    ws_delivery.fail_all()
    resp = alice.cancel(p.party_id)
    assert resp.status_code == 200 and alice.shows == "CANCELLED"
    pending = world.outbox_for(p.party_id, "PARTY_CANCELLED")
    assert {r[1] for r in pending} == {"PENDING"}

    ws_delivery.restore()
    attempts = len(ws_delivery.attempts)
    assert world.dispatch_pending() == 0                      # backoff: not due yet
    assert len(ws_delivery.attempts) == attempts
    clock.advance(seconds=campus_rules.backoff_seconds(1) + 1)
    assert world.dispatch_pending() == 2
    rows = world.outbox_for(p.party_id, "PARTY_CANCELLED")
    assert {r[1] for r in rows} == {"SENT"}
    pushed = [(u, m) for u, m in ws_delivery.sent if m.get("event_type") == "PARTY_CANCELLED"]
    assert sorted(u for u, _ in pushed) == sorted([world.uid("alice"), world.uid("bob")])
    assert pushed[0][1] == {"type": "party_event", "party_id": p.party_id, "version": 2,
                            "event_type": "PARTY_CANCELLED"}
    assert world.dispatch_pending() == 0                      # SENT rows are not pushed twice
    assert len(world.events_of(p.party_id)) == 2

    # a phone that missed even the push still converges, and the fetch acks the row
    bob.restart()
    bob.reconcile()
    assert (bob.cache.version, bob.cache.state) == (2, "CANCELLED")
    assert {r[1] for r in world.outbox_for(p.party_id, "PARTY_CANCELLED")
            if r[0] == world.uid("bob")} == {"ACKED"}


def test_pending_cancel_stays_pending_until_the_server_confirms(world):
    p = world.agree("alice", "bob")
    alice = world.device("alice")
    alice.reconcile()
    # the request never left the phone: pending journal entry only
    alice.pending_cancel = PendingCancel(p.party_id, "alice-cancel-never-sent")
    alice.reconcile()
    assert alice.cache.state == "AGREED" and alice.shows == "CANCEL_PENDING"
    assert world.events_of(p.party_id) == [(1, "PARTY_AGREED")]
    resp = alice.retry_cancel()
    assert resp.status_code == 200 and alice.pending_cancel is None
    assert alice.shows == "CANCELLED" and alice.cache.version == 2


# ==========================================================================
# (e) an unapproved third user cannot touch the party, chat or contacts
# ==========================================================================
def _ws(world, name, path):
    return world.client.websocket_connect(
        path, subprotocols=["token", world.headers(name)["Authorization"].removeprefix("Bearer ")])


def _relay(ws, receiver_id, **extra):
    ws.send_json({"type": "chat_message", "receiver_id": receiver_id, "content": "hello", **extra})


def test_unapproved_third_user_cannot_touch_party_chat_or_contact(world, clock, ws_delivery):
    p = world.agree("alice", "bob")
    pid = p.party_id
    alice, bob, carol = world.device("alice"), world.device("bob"), world.device("carol")
    secrets = [world.email("alice"), world.email("bob"), world.phones["alice"], world.phones["bob"]]

    def clean(resp):
        for s in secrets:
            assert s not in resp.text, s
        return resp

    # carol: same college, own OPEN request; dave and erin have a pending proposal
    rc = world.new_request("carol", 10, 120)
    world.new_request("dave", 10, 120)
    re_ = world.new_request("erin", 10, 120)
    pending = world.device("dave").propose(
        world.suggestion_for("dave", world.device("dave").get("/requests").json()[0]["id"],
                             "erin")["id"])
    assert pending.status_code == 201
    pending = pending.json()
    sugg_de = world.suggestion_for("erin", re_["id"], "dave")

    # suggestions never carry contact details (carol, dave, erin, and the earlier searches)
    csug = world.device("carol").search(rc["id"])
    assert csug.status_code == 200 and len(csug.json()["suggestions"]) == 2
    for resp in (csug, world.device("erin").search(re_["id"])):
        text = resp.text
        assert "@example.test" not in text and "+91" not in text
        assert "phone" not in text and "email" not in text

    # alice and bob chat while AGREED
    found = alice.get(f"/api/chat/conversations/find-or-create?partner_id={world.uid('bob')}")
    assert found.status_code == 200
    conv = found.json()["conversation_id"]
    sent = alice.post("/api/chat/messages", {"receiver_id": world.uid("bob"), "content": "gate at 6"})
    assert sent.status_code == 200 and sent.json()["conversation_id"] == conv
    assert sent.json()["created_at"].startswith("2026-03-01T04:00:00")
    assert bob.post("/api/chat/messages",
                    {"receiver_id": world.uid("alice"), "content": "ok"}).status_code == 200
    with _ws(world, "alice", "/api/ws/pool") as ws:
        _relay(ws, world.uid("bob"), party_id=pid)
        ws.send_json([])
        assert ws.receive_json()["type"] == "error"           # sync: the relay was processed
    relayed = [(u, m) for u, m in ws_delivery.sent if m.get("type") == "chat_message"]
    assert [(u, m["party_id"], m["sender_id"]) for u, m in relayed] == [
        (world.uid("bob"), pid, world.uid("alice"))]
    history = alice.get(f"/api/chat/messages/{conv}")
    assert [m["content"] for m in history.json()["messages"]] == ["gate at 6", "ok"]

    before_events = alice.get("/events").json()
    # --- carol: every party endpoint answers 404 and leaks nothing --------------------
    for method, path, body in (
        ("GET", f"/parties/{pid}", None),
        ("POST", f"/parties/{pid}/cancel", {"idempotency_key": "carol-1"}),
        ("POST", f"/parties/{pid}/changes", {"expected_version": 1, "note": "mine now"}),
        ("POST", f"/parties/{pid}/changes/1/approve", {"expected_party_version": 1}),
        ("POST", f"/parties/{pid}/report", {"outcome": "COMPLETED"}),
        ("PATCH", f"/parties/{pid}", {"expected_version": 1, "cost_note": "x"}),
        ("GET", f"/events?party_id={pid}", None),
    ):
        resp = clean(carol.call(method, path, body))
        assert resp.status_code == 404, (method, path, resp.text)
        assert resp.json() == {"detail": "Party not found"}
    own = carol.get("/parties/active").json()
    assert own["party"] is None and own["recently_ended"] is None
    nothing = carol.get("/events").json()
    assert nothing["party_id"] is None and nothing["events"] == [] and nothing["party"] is None

    # --- carol: chat is closed in every way -----------------------------------------
    for target in ("alice", "bob"):
        resp = clean(carol.get(f"/api/chat/conversations/find-or-create?partner_id={world.uid(target)}"))
        assert resp.status_code == 403 and resp.json()["detail"] == FORBIDDEN_CHAT
        resp = clean(carol.post("/api/chat/messages",
                                {"receiver_id": world.uid(target), "content": "psst"}))
        assert resp.status_code == 403
    assert clean(carol.get(f"/api/chat/messages/{conv}")).status_code == 403
    assert clean(carol.post(f"/api/chat/messages/{conv}/read")).status_code == 403
    assert clean(carol.get("/api/chat/conversations")).json() == {"conversations": []}
    for path in ("/api/ws/pool", "/api/ws/chat"):
        with _ws(world, "carol", path) as ws:
            for target in ("alice", "bob"):
                _relay(ws, world.uid(target), party_id=pid)
                frame = ws.receive_json()
                assert frame["type"] == "error" and frame["code"] == "not_authorized"
                assert frame["detail"] == FORBIDDEN_CHAT
    assert len([1 for _, m in ws_delivery.sent if m.get("type") == "chat_message"]) == 1

    # --- carol: someone else's proposal / suggestion -------------------------------
    cid = pending["id"]
    assert carol.get("/connections").json() == []
    for path, body in ((f"/connections/{cid}/accept",
                        {"expected_version": 1, "idempotency_key": "carol-2"}),
                       (f"/connections/{cid}/decline", {}),
                       (f"/connections/{cid}/withdraw", {}),
                       (f"/suggestions/{sugg_de['id']}/connections", {"acknowledge_warnings": False})):
        resp = carol.post(path, body)
        assert resp.status_code == 404, (path, resp.text)

    # nothing changed
    assert alice.get("/events").json()["events"] == before_events["events"]
    assert alice.get(f"/parties/{pid}").json()["state"] == "AGREED"
    still = world.device("dave").get("/connections").json()
    assert [(x["id"], x["state"]) for x in still] == [(cid, "PENDING")]
    assert len(alice.get(f"/api/chat/messages/{conv}").json()["messages"]) == 2

    # --- after the cancel, chat is refused but history stays readable --------------
    assert alice.cancel(pid).status_code == 200
    for dev, other in ((alice, "bob"), (bob, "alice")):
        assert dev.post("/api/chat/messages",
                        {"receiver_id": world.uid(other), "content": "too late"}).status_code == 403
        assert dev.get(
            f"/api/chat/conversations/find-or-create?partner_id={world.uid(other)}").status_code == 403
        assert len(dev.get(f"/api/chat/messages/{conv}").json()["messages"]) == 2
    with _ws(world, "alice", "/api/ws/chat") as ws:
        _relay(ws, world.uid("bob"), party_id=pid)
        assert ws.receive_json()["code"] == "not_authorized"
    listed = bob.get("/api/chat/conversations").json()["conversations"][0]["partner"]
    assert listed["phone_number"] is None and listed["email"] is None
    assert carol.get(f"/api/chat/messages/{conv}").status_code == 403


# ==========================================================================
# (f) provider outage never looks like "no partners"; arrive_by warnings
# ==========================================================================
def test_provider_outage_never_looks_like_no_partners(world, clock, provider):
    a = world.new_request("alice", 60, 120)
    b = world.new_request("bob", 60, 120)
    c = world.new_request("carol", 600, 660, arrive_by=620)    # earliest +30 min trip misses it
    d = world.new_request("dave", 600, 660)

    def look(who, req):
        body = world.suggestions(who, req["id"])
        assert len(body["suggestions"]) == 1, body            # never an empty "no partners"
        return body, body["suggestions"][0]

    provider.mode = "timeout"
    body, s = look("alice", a)
    assert body["estimate_status"] == "UNVERIFIED"
    assert s["estimate"]["status"] == "UNVERIFIED" and s["estimate"]["failure"] == "timeout"
    assert s["estimate"]["duration_s"] is None and s["other_request"]["id"] == b["id"]
    calls = provider.calls
    look("bob", b)                                            # inside the retry window: no new call
    assert provider.calls == calls
    _, sc = look("carol", c)
    assert sc["warnings"] == ["deadline_unverified"]

    clock.advance(seconds=campus_rules.ESTIMATE_RETRY_SECONDS + 1)
    provider.mode = "error"
    body, s = look("alice", a)
    assert body["estimate_status"] == "UNVERIFIED"
    assert s["estimate"]["failure"] == "unavailable" and provider.calls == calls + 1

    clock.advance(seconds=61)
    provider.mode = "ok"
    body, s2 = look("alice", a)
    assert body["estimate_status"] == "VERIFIED" and s2["id"] == s["id"]
    assert (s2["estimate"]["distance_m"], s2["estimate"]["duration_s"]) == (12000, 1800)
    assert s2["estimate"]["failure"] is None and s2["warnings"] == []

    # arrive_by: a verified 30 min trip departing at +600 cannot arrive by +620
    _, sc = look("carol", c)
    assert sc["warnings"] == ["cannot_meet_arrive_by"]
    carol = world.device("carol")
    refused = carol.propose(sc["id"])
    assert refused.status_code == 409 and code_of(refused) == "warnings_unacknowledged"
    assert refused.json()["detail"]["current"]["warnings"] == ["cannot_meet_arrive_by"]
    assert world.rows(cm.ConnectionProposal) == []
    ok = carol.propose(sc["id"], acknowledge_warnings=True)
    assert ok.status_code == 201 and ok.json()["state"] == "PENDING"
    # a pair without any deadline needs no acknowledgement
    _, sd = look("alice", a)
    assert world.device("alice").propose(sd["id"]).status_code == 201
    assert d["status"] == "OPEN"


# --------------------------------------------------------------------------
# (f2) arrive_by is judged against the EARLIEST feasible departure, not the window end
# --------------------------------------------------------------------------
def _arrive_by_pair(world, provider, window, arrive_by):
    provider.duration = 1800                                   # 30-minute trip
    a = world.new_request("alice", *window, arrive_by=arrive_by)
    b = world.new_request("bob", *window)
    return a, b, world.suggestion_for("alice", a["id"], "bob")


def test_arrive_by_uses_earliest_feasible_departure_so_a_late_window_end_is_fine(
        world, provider):
    # window 60..240, arrive_by 120: earliest 60 + 30 = 90 <= 120, although 240 + 30 > 120
    _, _, sugg = _arrive_by_pair(world, provider, (60, 240), 120)
    assert sugg["estimate"]["status"] == "VERIFIED" and sugg["estimate"]["duration_s"] == 1800
    assert sugg["warnings"] == []
    resp = world.device("alice").propose(sugg["id"])           # no acknowledgement needed
    assert resp.status_code == 201 and resp.json()["state"] == "PENDING"


def test_arrive_by_uses_earliest_feasible_departure_and_warns_when_it_cannot_meet_it(
        world, provider):
    # window 60..240, arrive_by 80: earliest 60 + 30 = 90 > 80
    _, _, sugg = _arrive_by_pair(world, provider, (60, 240), 80)
    assert sugg["warnings"] == ["cannot_meet_arrive_by"]
    alice = world.device("alice")
    refused = alice.propose(sugg["id"])
    assert refused.status_code == 409 and code_of(refused) == "warnings_unacknowledged"
    assert refused.json()["detail"]["current"]["warnings"] == ["cannot_meet_arrive_by"]
    assert world.rows(cm.ConnectionProposal) == []
    ok = alice.propose(sugg["id"], acknowledge_warnings=True)
    assert ok.status_code == 201 and ok.json()["state"] == "PENDING"


def test_arrive_by_uses_earliest_feasible_departure_which_moves_with_the_clock(
        world, provider, clock):
    # window 10..240, arrive_by 60: at 04:00 earliest is 04:10 -> 04:40 <= 05:00, no warning
    a, _, sugg = _arrive_by_pair(world, provider, (10, 240), 60)
    assert sugg["warnings"] == []
    # at 04:40 the feasible start (04:10) is in the past; max(start, now) = 04:40 -> 05:10 > 05:00
    clock.advance(minutes=40)
    later = world.suggestion_for("alice", a["id"], "bob")
    assert later["id"] == sugg["id"]
    assert later["feasible_window"]["start"]["utc"] == "2026-03-01T04:10:00Z"
    assert later["warnings"] == ["cannot_meet_arrive_by"]
    refused = world.device("alice").propose(later["id"])
    assert refused.status_code == 409 and code_of(refused) == "warnings_unacknowledged"
    assert world.device("alice").propose(later["id"], acknowledge_warnings=True).status_code == 201


# ==========================================================================
# (g) material change needs both approvals; completion reports are blind
# ==========================================================================
def test_material_change_requires_both_approvals_end_to_end(world, clock, ws_delivery):
    p = world.agree("alice", "bob")
    pid = p.party_id
    alice, bob = world.device("alice"), world.device("bob")
    original = p.party["agreed_departure"]["utc"]
    new_departure = clock.now + timedelta(minutes=45)
    new_utc = campus_time.utc_iso(new_departure)

    # alice proposes a new departure: the party itself does not change
    prop = alice.post(f"/parties/{pid}/changes",
                      {"expected_version": 1, "agreed_departure": new_departure.isoformat(),
                       "note": "bus was late"})
    assert prop.status_code == 201
    change = prop.json()
    assert change["state"] == "PENDING" and change["expected_party_version"] == 1
    assert change["new_departure"]["utc"] == new_utc and change["proposer_id"] == world.uid("alice")
    current = alice.get(f"/parties/{pid}").json()
    assert current["agreed_departure"]["utc"] == original and current["version"] == 2
    assert current["pending_change"]["id"] == change["id"]

    # bob's phone (still at v1) sees the pending change after reconciling
    bob.reconcile()
    assert bob.cache.version == 2 and bob.cache.departure == original
    assert bob.cache.pending_change["id"] == change["id"]
    assert bob.cache.pending_change["proposer_id"] == world.uid("alice")

    # the proposer cannot approve her own change; a stale version is refused
    own = alice.post(f"/parties/{pid}/changes/{change['id']}/approve", {"expected_party_version": 2})
    assert own.status_code == 403 and code_of(own) == "proposer_cannot_decide"
    stale = bob.post(f"/parties/{pid}/changes/{change['id']}/approve", {"expected_party_version": 1})
    assert stale.status_code == 409 and code_of(stale) == "stale_version"
    assert stale.json()["detail"]["current"]["party"]["agreed_departure"]["utc"] == original

    approved = bob.post(f"/parties/{pid}/changes/{change['id']}/approve", {"expected_party_version": 2})
    assert approved.status_code == 200
    view = approved.json()
    assert view["version"] == 3 and view["agreed_departure"]["utc"] == new_utc
    assert view["pending_change"] is None and view["state"] == "AGREED"

    alice.reconcile()
    bob.reconcile()
    for dev in (alice, bob):
        assert (dev.cache.version, dev.cache.state, dev.cache.departure) == (3, "AGREED", new_utc)
        assert dev.cache.pending_change is None
    assert alice.cache.event_types == ["PARTY_AGREED", "CHANGE_PROPOSED", "PARTY_CHANGED"]
    assert bob.cache.event_types == ["CHANGE_PROPOSED", "PARTY_CHANGED"]  # bob had v1 from accept

    # a rejected change leaves the party untouched; a note needs no approval
    meet = bob.post(f"/parties/{pid}/changes",
                    {"expected_version": 3, "meeting_landmark_id": world.landmarks["campus2"].id})
    assert meet.status_code == 201
    dup = alice.post(f"/parties/{pid}/changes", {"expected_version": 4, "note": "x",
                                                  "agreed_departure": new_departure.isoformat()})
    assert dup.status_code == 409 and code_of(dup) == "change_pending"
    rejected = alice.post(f"/parties/{pid}/changes/{meet.json()['id']}/reject",
                          {"expected_party_version": 4})
    assert rejected.status_code == 200 and rejected.json()["state"] == "REJECTED"
    note = alice.call("PATCH", f"/parties/{pid}", {"expected_version": 5, "cost_note": "split evenly"})
    assert note.status_code == 200 and note.json()["cost_note"] == "split evenly"
    alice.reconcile()
    bob.reconcile()
    final = bob.get(f"/parties/{pid}").json()
    assert final["meeting_landmark"]["name"] == "Main Gate" and final["version"] == 6
    assert alice.cache.version == bob.cache.version == 6
    feed = alice.get("/events?after_version=0").json()
    assert [(e["version"], e["event_type"]) for e in feed["events"]] == [
        (1, "PARTY_AGREED"), (2, "CHANGE_PROPOSED"), (3, "PARTY_CHANGED"),
        (4, "CHANGE_PROPOSED"), (5, "CHANGE_REJECTED"), (6, "NOTE_UPDATED")]


def test_completion_reports_are_blind_until_both_report(world, clock):
    p1 = world.agree("alice", "bob")
    p2 = world.agree("carol", "dave")
    p3 = world.agree("erin", "frank")
    alice, bob = world.device("alice"), world.device("bob")

    early = alice.post(f"/parties/{p1.party_id}/report", {"outcome": "COMPLETED"})
    assert early.status_code == 409 and code_of(early) == "report_too_early"
    assert alice.get(f"/parties/{p1.party_id}").json()["state"] == "AGREED"
    clock.advance(minutes=15)                                  # past the agreed departure

    # -- both COMPLETED -> COMPLETED --------------------------------------------------
    first = alice.post(f"/parties/{p1.party_id}/report", {"outcome": "COMPLETED"})
    assert first.status_code == 200 and first.json()["state"] == "AGREED"
    mine = {m["you"]: m for m in first.json()["members"]}
    assert mine[True]["report_outcome"] == "COMPLETED" and mine[False]["report_outcome"] is None
    seen_by_bob = {m["user_id"]: m for m in bob.get(f"/parties/{p1.party_id}").json()["members"]}
    assert seen_by_bob[world.uid("alice")]["report_outcome"] is None      # hidden from the partner
    assert seen_by_bob[world.uid("bob")]["report_outcome"] is None
    feed = bob.get(f"/events?after_version=1&party_id={p1.party_id}").json()
    assert [e["event_type"] for e in feed["events"]] == ["REPORT_RECORDED"]
    assert "outcome" not in str(feed["events"][0]["payload"]).lower()
    done = bob.post(f"/parties/{p1.party_id}/report", {"outcome": "COMPLETED"})
    assert done.status_code == 200 and done.json()["state"] == "COMPLETED"
    assert done.json()["end_reason"] == "completed"
    revealed = {m["user_id"]: m["report_outcome"] for m in done.json()["members"]}
    assert revealed == {world.uid("alice"): "COMPLETED", world.uid("bob"): "COMPLETED"}
    assert done.json()["partner"]["phone_number"] is None
    assert world.events_of(p1.party_id) == [
        (1, "PARTY_AGREED"), (2, "REPORT_RECORDED"), (3, "REPORT_RECORDED"), (4, "PARTY_COMPLETED")]
    for dev, req in ((alice, p1.ra), (bob, p1.rb)):
        assert dev.get(f"/requests/{req['id']}").json()["status"] == "FULFILLED"
    ended = alice.get("/parties/active").json()
    assert ended["party"] is None and ended["recently_ended"]["state"] == "COMPLETED"

    # -- mixed outcomes -> DISPUTED (a report may be changed until the partner reports) --
    carol, dave = world.device("carol"), world.device("dave")
    assert carol.post(f"/parties/{p2.party_id}/report", {"outcome": "COMPLETED"}).status_code == 200
    changed = carol.post(f"/parties/{p2.party_id}/report", {"outcome": "DID_NOT_HAPPEN"})
    assert changed.status_code == 200 and changed.json()["state"] == "AGREED"
    assert [m["report_outcome"] for m in dave.get(f"/parties/{p2.party_id}").json()["members"]
            if not m["you"]] == [None]
    disputed = dave.post(f"/parties/{p2.party_id}/report", {"outcome": "COMPLETED"})
    assert disputed.status_code == 200 and disputed.json()["state"] == "DISPUTED"
    assert disputed.json()["end_reason"] == "disputed"
    assert {m["user_id"]: m["report_outcome"] for m in disputed.json()["members"]} == {
        world.uid("carol"): "DID_NOT_HAPPEN", world.uid("dave"): "COMPLETED"}
    assert world.events_of(p2.party_id)[-1] == (5, "PARTY_DISPUTED")
    for dev, req in ((carol, p2.ra), (dave, p2.rb)):
        assert dev.get(f"/requests/{req['id']}").json()["status"] == "CANCELLED"
    assert all(not m.active for m in world.rows(cm.PartyMember, party_id=p2.party_id))

    # -- both DID_NOT_HAPPEN -> CANCELLED("did_not_happen") ----------------------------
    erin, frank = world.device("erin"), world.device("frank")
    assert erin.post(f"/parties/{p3.party_id}/report", {"outcome": "DID_NOT_HAPPEN"}).status_code == 200
    final = frank.post(f"/parties/{p3.party_id}/report", {"outcome": "DID_NOT_HAPPEN"})
    assert final.status_code == 200 and final.json()["state"] == "CANCELLED"
    assert final.json()["end_reason"] == "did_not_happen"
    # a late repeat of the report that ended it is an idempotent no-op
    again = frank.post(f"/parties/{p3.party_id}/report", {"outcome": "DID_NOT_HAPPEN"})
    assert again.status_code == 200 and again.json()["version"] == final.json()["version"]
    flip = frank.post(f"/parties/{p3.party_id}/report", {"outcome": "COMPLETED"})
    assert flip.status_code == 409 and code_of(flip) == "party_not_active"


# ==========================================================================
# (h) the demo script: two devices, whole life of a party (+ transcript)
# ==========================================================================
def test_full_happy_path_with_two_devices(world, clock, ws_delivery):
    t = Transcript(lambda: clock.now)
    world.record(t)
    alice, bob = world.device("alice"), world.device("bob")

    t.section("1. Both students look at their campus's landmarks and post a trip request")
    lm = alice.get("/landmarks")
    assert lm.status_code == 200
    assert {x["name"]: x["kind"] for x in lm.json()} == {
        "Main Gate": "CAMPUS_POINT", "Airport Terminal": "HUB", "Library": "CAMPUS_POINT"}
    ra = alice.create_request(world.request_body(30, 150, arrive_by=240))
    rb = bob.create_request(world.request_body(60, 180))
    assert (ra.status_code, rb.status_code) == (201, 201)
    ra, rb = ra.json(), rb.json()

    t.section("2. Each searches: the windows overlap, the estimate comes from the (fake) provider")
    sa = alice.search(ra["id"])
    sb = bob.search(rb["id"])
    assert sa.status_code == sb.status_code == 200
    sug = sa.json()["suggestions"][0]
    assert sug["id"] == sb.json()["suggestions"][0]["id"]
    assert sug["reason"] == "WINDOW_OVERLAP" and sug["warnings"] == []
    assert sug["estimate"]["status"] == "VERIFIED"
    assert_no_contact(sa.text + sb.text, world, "alice", "bob")

    t.section("3. Alice proposes, Bob sees it as incoming and accepts: a party is agreed")
    conn = alice.propose(sug["id"])
    assert conn.status_code == 201 and conn.json()["state"] == "PENDING"
    incoming = bob.get("/connections?role=incoming")
    assert [x["id"] for x in incoming.json()] == [conn.json()["id"]]
    acc = bob.accept(conn.json()["id"], conn.json()["version"])
    assert acc.status_code == 200
    party = acc.json()["party"]
    pid = party["id"]
    assert party["state"] == "AGREED" and party["version"] == 1
    assert party["partner"]["phone_number"] == world.phones["alice"]
    assert party["agreed_departure"]["utc"] == "2026-03-01T05:00:00Z"
    assert party["transport_responsibility"].startswith("Participants arrange and pay")

    t.section("4. Alice's phone reconciles over REST (sockets are only an accelerator)")
    alice.reconcile()
    assert alice.cache.version == bob.cache.version == 1
    assert alice.cache.state == bob.cache.state == "AGREED"

    t.section("5. They chat while the party is AGREED")
    partner = world.uid("bob")
    found = alice.get(f"/api/chat/conversations/find-or-create?partner_id={partner}")
    assert found.status_code == 200
    conv = found.json()["conversation_id"]
    msg = alice.post("/api/chat/messages", {"receiver_id": partner, "content": "I'll wait at the gate"})
    assert msg.status_code == 200
    assert bob.post(f"/api/chat/messages/{conv}/read").json() == {"marked_read": 1}
    got = bob.get(f"/api/chat/messages/{conv}")
    assert [(m["content"], m["is_read"]) for m in got.json()["messages"]] == [
        ("I'll wait at the gate", True)]

    t.section("6. A material change (new departure) needs the other member's approval")
    later = clock.now + timedelta(minutes=90)
    change = alice.post(f"/parties/{pid}/changes",
                        {"expected_version": 1, "agreed_departure": later.isoformat(),
                         "note": "10 minutes later please"})
    assert change.status_code == 201
    bob.reconcile()
    assert bob.cache.pending_change["id"] == change.json()["id"]
    assert bob.cache.departure == "2026-03-01T05:00:00Z"      # unchanged until approved
    ok = bob.post(f"/parties/{pid}/changes/{change.json()['id']}/approve",
                  {"expected_party_version": bob.cache.version})
    assert ok.status_code == 200 and ok.json()["version"] == 3
    alice.reconcile()
    bob.reconcile()
    assert alice.cache.version == bob.cache.version == 3
    assert alice.cache.departure == bob.cache.departure == campus_time.utc_iso(later)

    t.section("7. After the departure both report; completion is self-reported, not GPS proof")
    clock.advance(minutes=100)
    r1 = alice.post(f"/parties/{pid}/report", {"outcome": "COMPLETED"})
    assert r1.status_code == 200 and r1.json()["state"] == "AGREED"
    r2 = bob.post(f"/parties/{pid}/report", {"outcome": "COMPLETED"})
    assert r2.status_code == 200 and r2.json()["state"] == "COMPLETED"
    alice.reconcile()
    bob.reconcile()
    assert alice.cache.state == bob.cache.state == "COMPLETED"
    assert alice.cache.version == bob.cache.version == r2.json()["version"]

    t.section("8. Afterwards: contact details are hidden and chat is closed, history stays")
    ended = alice.get("/parties/active").json()["recently_ended"]
    assert ended["partner"]["phone_number"] is None and ended["partner"]["email"] is None
    late = alice.post("/api/chat/messages", {"receiver_id": partner, "content": "thanks!"})
    assert late.status_code == 403
    assert len(alice.get(f"/api/chat/messages/{conv}").json()["messages"]) == 1
    assert alice.get(f"/requests/{ra['id']}").json()["status"] == "FULFILLED"

    # the transcript is sanitized no matter whether it is written out
    t.assert_sanitized()
    text = t.render()
    assert text.splitlines()[2] == (
        "> Recorded from the automated acceptance test with a fake clock "
        "and a fake routing provider (no live provider)")
    target = os.environ.get("TRIPSYNC_E2E_TRANSCRIPT")
    if target:
        out = Path(target)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")


# ==========================================================================
# recorded proof of RECOVERY (TRIPSYNC_E2E_RECONCILE_TRANSCRIPT=<path>)
# ==========================================================================
@contextmanager
def _quiet(world, transcript):
    """Setup calls that are not part of the story are not recorded."""
    world.record(None)
    try:
        yield
    finally:
        world.record(transcript)


def test_recorded_recovery_reconciliation_and_competing_accepts(world, clock, ws_delivery):
    t = Transcript(lambda: clock.now, title="TripSync campus scheduling: recovery transcript",
                   compact=True)
    world.record(t)
    alice, bob = world.device("alice"), world.device("bob")

    # ---------------------------------------------------------------- 1
    t.section("1. A party is AGREED and both phones show the same version")
    with _quiet(world, t):
        p = world.agree("alice", "bob")
    pid = p.party_id
    t.note("Setup elided: both students posted requests, searched, Alice proposed and Bob accepted "
           "(see the happy-path transcript).")
    alice.reconcile()
    bob.reconcile()
    assert (alice.cache.version, alice.cache.state) == (bob.cache.version, bob.cache.state) == (1, "AGREED")
    t.note("Phone state: Alice shows AGREED v1, Bob shows AGREED v1.")

    # ---------------------------------------------------------------- 2
    t.section("2. Push delivery is down; Alice cancels; the server commits but the reply is lost")
    ws_delivery.fail_all()
    t.note("Client side (not an API call): Alice's phone first writes 'cancel pending' with its "
           "idempotency key to local storage, then sends the request.")
    assert alice.cancel(pid, drop_response=True) is None
    key = alice.pending_cancel.key
    t.note("Client side (not an API call): the reply never arrives. Alice's phone shows 'cancel "
           "pending' and still caches AGREED v1; Bob's phone has heard nothing and shows AGREED v1.")
    assert alice.shows == "CANCEL_PENDING" and bob.shows == "AGREED"
    assert world.events_of(pid) == [(1, "PARTY_AGREED"), (2, "PARTY_CANCELLED")]
    rows = world.outbox_for(pid, "PARTY_CANCELLED")
    assert {r[1] for r in rows} == {"PENDING"} and len(rows) == 2
    t.note("Server side (asserted by the test, not an API call): exactly one PARTY_CANCELLED event "
           "(version 2) exists, and the notification for each member is still pending retry, not lost.")

    # ---------------------------------------------------------------- 3
    t.section("3. Alice retries with the SAME idempotency key: stored result, no second event")
    retry = alice.retry_cancel()
    assert retry.status_code == 200 and retry.headers["Idempotent-Replay"] == "true"
    assert retry.json()["version"] == 2 and retry.json()["state"] == "CANCELLED"
    assert world.events_of(pid) == [(1, "PARTY_AGREED"), (2, "PARTY_CANCELLED")]
    assert alice.pending_cancel is None
    t.note("Phone state: the stored response resolves Alice's 'cancel pending'. The server still "
           "holds one PARTY_CANCELLED event.")
    assert key == "alice-cancel-1"

    # ---------------------------------------------------------------- 4
    t.section("4. Both phones restart with empty caches and converge from REST alone")
    alice.restart()
    bob.restart()
    t.note("Client side (not an API call): both apps restart; every in-memory cache is empty.")
    alice.reconcile()
    bob.reconcile()
    for dev in (alice, bob):
        assert (dev.cache.party_id, dev.cache.version, dev.cache.state) == (pid, 2, "CANCELLED")
        assert dev.cache.event_types == ["PARTY_AGREED", "PARTY_CANCELLED"]
    t.note("Phone state: Alice and Bob both show CANCELLED v2; contact details are null and only "
           "names remain.")
    ended = bob.get("/parties/active").json()["recently_ended"]
    assert ended["partner"]["phone_number"] is None and ended["partner"]["email"] is None

    # ---------------------------------------------------------------- 5
    t.section("5. Bob's request is OPEN again; Alice's is CANCELLED")
    mine = bob.get(f"/requests/{p.rb['id']}")
    assert mine.status_code == 200 and mine.json()["status"] == "OPEN"
    hers = alice.get(f"/requests/{p.ra['id']}")
    assert hers.json()["status"] == "CANCELLED"

    # ---------------------------------------------------------------- 6
    t.section("6. Delivery is restored and the outbox dispatcher runs")
    ws_delivery.restore()
    clock.advance(minutes=1)
    assert world.dispatch_pending() == 0
    assert {r[1] for r in world.outbox_for(pid, "PARTY_CANCELLED")} == {"ACKED"}
    t.note("Server side (not an API call): the dispatcher finds nothing left to push, because "
           "each phone's GET /events already acknowledged its notification. Nothing is pushed twice.")

    # ---------------------------------------------------------------- 7
    t.section("7. Same outage, but the phone stays online: the outbox retry delivers later")
    with _quiet(world, t):
        q = world.agree("carol", "dave")
    carol, dave = world.device("carol"), world.device("dave")
    t.note("Setup elided: Carol and Dave agreed a party.")
    ws_delivery.fail_all()
    done = carol.cancel(q.party_id)
    assert done.status_code == 200 and done.json()["state"] == "CANCELLED"
    assert {r[1] for r in world.outbox_for(q.party_id, "PARTY_CANCELLED")} == {"PENDING"}
    t.note("Server side (not an API call): the cancel succeeded for Carol, but both notifications "
           "are pending because no socket accepted them.")
    ws_delivery.restore()
    assert world.dispatch_pending() == 0
    clock.advance(seconds=campus_rules.backoff_seconds(1) + 1)
    assert world.dispatch_pending() == 2
    assert {r[1] for r in world.outbox_for(q.party_id, "PARTY_CANCELLED")} == {"SENT"}
    t.note("Server side (not an API call): delivery is back; once the retry backoff has passed the "
           "dispatcher pushes both notifications and marks them sent. A second run pushes nothing.")
    assert world.dispatch_pending() == 0
    dave.reconcile()
    assert (dave.cache.version, dave.cache.state) == (2, "CANCELLED")
    t.note("Phone state: even a push is only an accelerator; Dave's reconcile shows CANCELLED v2.")

    # ---------------------------------------------------------------- 8
    t.section("8. Two proposals compete for one student: exactly one wins")
    t.note("The accepts below run one after the other so the transcript is deterministic. The "
           "genuinely concurrent proof (threads released by a barrier, SQLite and Postgres) is "
           "test_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party.")
    erin = world.device("erin")
    with _quiet(world, t):
        re_ = world.new_request("erin", 10, 120)
        rf = world.new_request("frank", 10, 120)
        rg = world.new_request("grace", 10, 120)
        from_frank = world.device("frank").propose(
            world.suggestion_for("frank", rf["id"], "erin")["id"]).json()
        from_grace = world.device("grace").propose(
            world.suggestion_for("grace", rg["id"], "erin")["id"]).json()
    t.note("Setup elided: Frank and Grace each proposed to Erin.")
    inbox = erin.get("/connections?role=incoming")
    assert sorted(x["id"] for x in inbox.json()) == sorted([from_frank["id"], from_grace["id"]])
    won = erin.accept(from_frank["id"], from_frank["version"], key="erin-accept-frank")
    assert won.status_code == 200 and won.json()["party"]["state"] == "AGREED"
    lost = erin.accept(from_grace["id"], from_grace["version"], key="erin-accept-grace")
    assert lost.status_code == 409
    detail = lost.json()["detail"]
    assert detail["code"] in ("already_resolved", "participant_busy")
    assert set(detail["current"]) == {"proposal", "active_party"}
    assert detail["current"]["active_party"]["id"] == won.json()["party"]["id"]   # Erin's own party
    assert world.email("grace") not in lost.text and world.phones["grace"] not in lost.text
    follow = erin.get("/connections?state=EXPIRED")
    assert [x["id"] for x in follow.json()] == [from_grace["id"]]
    assert follow.json()[0]["state"] == "EXPIRED"
    assert world.device("grace").get("/requests").json()[0]["status"] == "OPEN"
    t.note("Phone state: Erin sees the winning party and Grace's proposal as EXPIRED; Grace's "
           "request is still OPEN and searchable.")

    t.assert_sanitized()
    assert world_lines(t) < 900
    target = os.environ.get("TRIPSYNC_E2E_RECONCILE_TRANSCRIPT")
    if target:
        out = Path(target)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(t.render(), encoding="utf-8")


def world_lines(transcript):
    return len(transcript.render().splitlines())
