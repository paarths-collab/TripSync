"""Connection proposals: create / list / accept / decline / withdraw, 409 codes,
idempotency and (threaded, SQLite) concurrent accepts. Fictional data only."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core import campus_time
from app.db.database import Base
from app.models import campus_model as cm
from app.models import user_model
from app.schemas import campus_schema as schemas
from app.services import campus_party_service as svc
from tests.campus_party_helpers import (  # noqa: F401  (world is a fixture)
    API, race, seed_college, seed_party, seed_proposal, seed_request, seed_user, world,
)

RS = cm.TravelRequestStatus
PS = cm.ProposalState


def code(resp):
    return resp.json()["detail"]["code"]


# =========================================================== creating proposals
def test_create_proposal_happy_path(world):
    p = world.pair("alice", "bob")
    body = p.proposal
    assert body["state"] == "PENDING" and body["version"] == 1
    assert body["direction"] == "outgoing"
    assert body["proposer"]["user_id"] == world.users["alice"].id
    assert body["recipient"]["user_id"] == world.users["bob"].id
    # no contact details anywhere in the proposal
    text = json.dumps(body)
    assert "@example.test" not in text and "+91" not in text
    row = world.get(cm.ConnectionProposal, body["id"])
    assert (row.proposer_request_version, row.recipient_request_version) == (1, 1)
    assert row.pair_low_request_id < row.pair_high_request_id
    # creating a proposal reserves nothing
    assert world.get(cm.TravelRequest, p.ra.id).status == RS.OPEN
    assert world.get(cm.TravelRequest, p.rb.id).status == RS.OPEN


def test_proposal_is_pushed_to_recipient_after_commit(world, ws_delivery):
    world.pair("alice", "bob")
    assert [uid for uid, _ in ws_delivery.sent] == [world.users["bob"].id]
    msg = ws_delivery.sent[0][1]
    assert msg["type"] == "connection_proposed"
    assert msg["proposal"]["direction"] == "incoming"


def test_proposal_survives_a_dead_socket(world, ws_delivery):
    ws_delivery.fail_all()
    p = world.pair("alice", "bob")
    assert world.get(cm.ConnectionProposal, p.proposal["id"]).state == PS.PENDING


def test_expires_at_is_ttl_capped_by_earliest_window_end(world):
    long = world.pair("alice", "bob", start=5, end=200)
    exp = campus_time.from_db(world.get(cm.ConnectionProposal, long.proposal["id"]).expires_at)
    assert exp == world.clock.now + timedelta(minutes=30)
    short = world.pair("carol", "dave", start=-5, end=20)
    exp = campus_time.from_db(world.get(cm.ConnectionProposal, short.proposal["id"]).expires_at)
    assert exp == world.clock.now + timedelta(minutes=20)


def test_create_requires_owning_one_of_the_requests(world):
    ra, rb = world.new_request("alice"), world.new_request("bob")
    sid = world.suggestion(ra, rb)
    assert world.propose("carol", sid).status_code == 404
    assert world.propose("alice", 99999).status_code == 404


def test_create_rejects_pair_that_is_no_longer_eligible(world):
    ra, rb = world.new_request("alice", 10, 60), world.new_request("bob", 100, 150)
    sid = world.suggestion(ra, rb)
    resp = world.propose("alice", sid)
    assert resp.status_code == 409 and code(resp) == "not_eligible"
    assert resp.json()["detail"]["current"]["reason"] == "disjoint_windows"

    rc = world.new_request("carol", status="RESERVED")
    sid = world.suggestion(world.new_request("dave"), rc)
    assert code(world.propose("dave", sid)) == "not_eligible"


def test_warnings_must_be_acknowledged(world):
    ra, rb = world.new_request("alice"), world.new_request("bob")
    sid = world.suggestion(ra, rb, warnings=["deadline_unverified"])
    resp = world.propose("alice", sid)
    assert resp.status_code == 409 and code(resp) == "warnings_unacknowledged"
    assert resp.json()["detail"]["current"]["warnings"] == ["deadline_unverified"]
    assert world.rows(cm.ConnectionProposal) == []
    assert world.propose("alice", sid, ack=True).status_code == 201


@pytest.mark.parametrize("second_by", ["alice", "bob"])
def test_duplicate_pending_proposal_is_rejected_in_either_direction(world, second_by):
    p = world.pair("alice", "bob")
    resp = world.propose(second_by, p.suggestion_id)
    assert resp.status_code == 409 and code(resp) == "duplicate_proposal"
    assert resp.json()["detail"]["current"]["proposal"]["id"] == p.proposal["id"]
    assert len(world.rows(cm.ConnectionProposal)) == 1


def test_overdue_pending_proposal_does_not_block_a_new_one(world):
    p = world.pair("alice", "bob")
    world.clock.advance(minutes=31)
    resp = world.propose("bob", p.suggestion_id)
    assert resp.status_code == 201
    assert world.get(cm.ConnectionProposal, p.proposal["id"]).state == PS.EXPIRED


# ================================================================= listing
def test_list_connections_roles_state_and_lazy_expiry(world):
    p1 = world.pair("alice", "bob")
    p2 = world.pair("carol", "alice")
    h = world.headers["alice"]
    allp = world.client.get(f"{API}/connections", headers=h).json()
    assert {x["id"] for x in allp} == {p1.proposal["id"], p2.proposal["id"]}
    out = world.client.get(f"{API}/connections?role=outgoing", headers=h).json()
    assert [x["id"] for x in out] == [p1.proposal["id"]] and out[0]["direction"] == "outgoing"
    inc = world.client.get(f"{API}/connections?role=incoming", headers=h).json()
    assert [x["id"] for x in inc] == [p2.proposal["id"]] and inc[0]["direction"] == "incoming"
    assert world.client.get(f"{API}/connections?role=bogus", headers=h).status_code == 422
    assert world.client.get(f"{API}/connections?state=BOGUS", headers=h).status_code == 422
    # a third user sees nothing
    assert world.client.get(f"{API}/connections", headers=world.headers["dave"]).json() == []

    world.clock.advance(minutes=31)
    expired = world.client.get(f"{API}/connections?state=EXPIRED", headers=h).json()
    assert {x["id"] for x in expired} == {p1.proposal["id"], p2.proposal["id"]}
    assert world.client.get(f"{API}/connections?state=PENDING", headers=h).json() == []


# ================================================================== accept
def test_accept_happy_path_creates_party_in_one_transaction(world):
    p = world.pair("alice", "bob")
    resp = world.accept("bob", p.proposal["id"], 1, key="acc-1")
    assert resp.status_code == 200, resp.text
    assert "idempotent-replay" not in resp.headers
    body = resp.json()
    assert body["connection"]["state"] == "ACCEPTED" and body["connection"]["version"] == 2
    party = body["party"]
    assert party["state"] == "AGREED" and party["version"] == 1
    assert party["transport_responsibility"].startswith("Participants arrange and pay")
    assert party["meeting_landmark"]["id"] == world.landmarks["campus"].id
    assert party["hub"]["id"] == world.landmarks["hub"].id
    assert party["direction"] == "TO_HUB"
    # agreed departure = feasible window start (now + 10 min), local time rendered
    dep = campus_time.from_db(world.get(cm.TravelParty, party["id"]).agreed_departure)
    assert dep == world.clock.now + timedelta(minutes=10)
    assert party["agreed_departure"]["timezone"] == "Asia/Kolkata"
    assert party["agreed_departure"]["local"].endswith("+05:30")
    # contacts: partner phone/email while AGREED
    assert party["partner"]["user_id"] == world.users["alice"].id
    assert party["partner"]["phone_number"] == "+910000000001"
    assert party["partner"]["email"] == "alice@example.test"
    assert {m["user_id"]: m["you"] for m in party["members"]} == {
        world.users["alice"].id: False, world.users["bob"].id: True}

    # persisted state
    prop = world.get(cm.ConnectionProposal, p.proposal["id"])
    assert prop.state == PS.ACCEPTED and prop.party_id == party["id"] and prop.resolved_at
    members = world.rows(cm.PartyMember, party_id=party["id"])
    assert sorted(m.user_id for m in members) == sorted(u.id for u in (world.users["alice"], world.users["bob"]))
    assert all(m.active for m in members)
    for r in (p.ra, p.rb):
        row = world.get(cm.TravelRequest, r.id)
        assert row.status == RS.RESERVED and row.version == 2
    events = world.events(party["id"])
    assert [(e.version, e.event_type) for e in events] == [(1, "PARTY_AGREED")]
    outbox = world.rows(cm.OutboxMessage)
    assert sorted(o.recipient_id for o in outbox) == sorted(
        [world.users["alice"].id, world.users["bob"].id])
    rec = world.rows(cm.IdempotencyRecord)
    assert len(rec) == 1 and rec[0].operation == "accept_connection" and rec[0].target_id == p.proposal["id"]


def test_accept_dispatches_outbox_after_commit_best_effort(world, monkeypatch):
    from app.services import campus_outbox

    seen = []

    async def spy(db, party_id):
        # state must already be committed when dispatch runs
        seen.append((party_id, world.get(cm.TravelParty, party_id).state))
        raise RuntimeError("socket layer down")

    monkeypatch.setattr(campus_outbox, "dispatch_for_party", spy)
    p = world.pair("alice", "bob")
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 200  # a dispatch failure never fails the request
    assert seen == [(resp.json()["party"]["id"], cm.PartyState.AGREED)]


def test_accept_is_recipient_only(world):
    p = world.pair("alice", "bob")
    pid = p.proposal["id"]
    for who in ("alice", "carol"):
        r = world.client.post(f"{API}/connections/{pid}/accept", headers=world.headers[who],
                              json={"expected_version": 1, "idempotency_key": "x"})
        assert r.status_code == 404
    assert world.client.post(f"{API}/connections/9999/accept", headers=world.headers["bob"],
                             json={"expected_version": 1, "idempotency_key": "x"}).status_code == 404
    assert world.get(cm.ConnectionProposal, pid).state == PS.PENDING


def test_accept_validates_body(world):
    p = world.pair("alice", "bob")
    r = world.client.post(f"{API}/connections/{p.proposal['id']}/accept",
                          headers=world.headers["bob"], json={"expected_version": 1})
    assert r.status_code == 422


def test_accept_already_resolved(world):
    p = world.pair("alice", "bob")
    pid = p.proposal["id"]
    assert world.client.post(f"{API}/connections/{pid}/decline", headers=world.headers["bob"],
                             json={}).status_code == 200
    resp = world.accept("bob", pid, 2)
    assert resp.status_code == 409 and code(resp) == "already_resolved"
    cur = resp.json()["detail"]["current"]
    assert cur["proposal"]["state"] == "DECLINED" and cur["active_party"] is None
    assert world.rows(cm.TravelParty) == []


def test_accept_expired_marks_proposal_expired(world):
    p = world.pair("alice", "bob")
    world.clock.advance(minutes=31)
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "expired"
    assert resp.json()["detail"]["current"]["proposal"]["state"] == "EXPIRED"
    row = world.get(cm.ConnectionProposal, p.proposal["id"])
    assert row.state == PS.EXPIRED and row.version == 2
    assert world.get(cm.TravelRequest, p.ra.id).status == RS.OPEN
    assert world.rows(cm.TravelParty) == []


def test_accept_stale_proposal_version(world):
    p = world.pair("alice", "bob")
    resp = world.accept("bob", p.proposal["id"], 7)
    assert resp.status_code == 409 and code(resp) == "stale_version"
    assert resp.json()["detail"]["current"]["proposal"]["version"] == 1
    assert world.rows(cm.TravelParty) == []


def test_accept_request_changed_when_version_bumped(world):
    p = world.pair("alice", "bob")
    db = world.sf()
    row = db.get(cm.TravelRequest, p.rb.id)
    row.version += 1  # e.g. PATCH /requests/{id} after the proposal
    db.commit()
    db.close()
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "request_changed"
    assert world.rows(cm.TravelParty) == []


def test_accept_request_changed_when_request_no_longer_open(world):
    p = world.pair("alice", "bob")
    db = world.sf()
    db.get(cm.TravelRequest, p.ra.id).status = RS.CANCELLED
    db.commit()
    db.close()
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "request_changed"


def test_accept_not_eligible_when_windows_drift_apart(world):
    p = world.pair("alice", "bob")
    db = world.sf()
    r = db.get(cm.TravelRequest, p.ra.id)  # window moved without a version bump
    r.earliest_departure = campus_time.to_db(world.clock.now + timedelta(minutes=300))
    r.latest_departure = campus_time.to_db(world.clock.now + timedelta(minutes=360))
    r.expires_at = r.latest_departure
    db.commit()
    db.close()
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "not_eligible"


def test_accept_participant_busy(world):
    # alice has two OPEN requests; proposals arrive on both.
    r1, r2 = world.new_request("alice", 10, 120), world.new_request("alice", 200, 300)
    rb, rc = world.new_request("bob", 10, 120), world.new_request("carol", 200, 300)
    s1, s2 = world.suggestion(r1, rb), world.suggestion(r2, rc)
    p1 = world.propose("bob", s1).json()
    p2 = world.propose("carol", s2).json()
    assert world.accept("alice", p1["id"], 1, key="a").status_code == 200
    resp = world.accept("alice", p2["id"], 1, key="b")
    assert resp.status_code == 409 and code(resp) == "participant_busy"
    # the caller sees their OWN active party
    assert resp.json()["detail"]["current"]["active_party"]["state"] == "AGREED"
    assert len(world.rows(cm.TravelParty)) == 1
    assert world.get(cm.TravelRequest, rc.id).status == RS.OPEN


def test_accept_window_closed(world):
    world.clock.set(world.clock.now + timedelta(seconds=10))  # not on a minute boundary
    p = world.pair("alice", "bob", start=-30, end=0.5)
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "window_closed"
    assert world.rows(cm.TravelParty) == []
    assert world.get(cm.TravelRequest, p.ra.id).status == RS.OPEN


def test_accept_departure_is_clamped_to_next_minute_when_window_already_started(world):
    world.clock.set(world.clock.now + timedelta(seconds=10))
    p = world.pair("alice", "bob", start=-30, end=120)
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 200
    dep = campus_time.from_db(world.get(cm.TravelParty, resp.json()["party"]["id"]).agreed_departure)
    assert dep == world.clock.now.replace(second=0) + timedelta(minutes=1)


def test_accepting_expires_competing_proposals_touching_either_request(world):
    ra = world.new_request("alice")
    rb = world.new_request("bob")
    rc = world.new_request("carol")
    rd = world.new_request("dave")
    p_ab = world.propose("alice", world.suggestion(ra, rb)).json()
    p_cb = world.propose("carol", world.suggestion(rc, rb)).json()   # touches bob's request
    p_ad = world.propose("dave", world.suggestion(rd, ra)).json()    # touches alice's request
    p_cd = world.propose("carol", world.suggestion(rc, rd)).json()   # unrelated
    assert world.accept("bob", p_ab["id"], 1).status_code == 200
    state = lambda pid: world.get(cm.ConnectionProposal, pid).state  # noqa: E731
    assert state(p_ab["id"]) == PS.ACCEPTED
    assert state(p_cb["id"]) == PS.EXPIRED and state(p_ad["id"]) == PS.EXPIRED
    assert state(p_cd["id"]) == PS.PENDING
    assert world.get(cm.TravelRequest, rc.id).status == RS.OPEN
    assert world.get(cm.TravelRequest, rd.id).status == RS.OPEN


def test_sequential_accepts_for_one_student_exactly_one_party(world):
    """bob receives proposals from alice and carol on the same request."""
    rb = world.new_request("bob")
    ra, rc = world.new_request("alice"), world.new_request("carol")
    p_a = world.propose("alice", world.suggestion(ra, rb)).json()
    p_c = world.propose("carol", world.suggestion(rc, rb)).json()
    assert world.accept("bob", p_a["id"], 1, key="one").status_code == 200
    resp = world.accept("bob", p_c["id"], 1, key="two")
    assert resp.status_code == 409 and code(resp) == "already_resolved"
    assert len(world.rows(cm.TravelParty)) == 1
    assert world.get(cm.TravelRequest, rc.id).status == RS.OPEN
    assert world.get(cm.TravelRequest, rb.id).status == RS.RESERVED
    assert len(world.events(world.rows(cm.TravelParty)[0].id, "PARTY_AGREED")) == 1


def test_loser_conflict_never_leaks_the_winners_party(world):
    """carol -> alice and alice -> dave compete for alice's request. After alice
    accepts carol, dave (not a member) must only see his own proposal state."""
    ra, rc, rd = world.new_request("alice"), world.new_request("carol"), world.new_request("dave")
    p_ca = world.propose("carol", world.suggestion(rc, ra)).json()
    p_ad = world.propose("alice", world.suggestion(ra, rd)).json()
    won = world.accept("alice", p_ca["id"], 1, key="w")
    assert won.status_code == 200
    party_id = won.json()["party"]["id"]

    resp = world.accept("dave", p_ad["id"], 1, key="l")
    assert resp.status_code == 409 and code(resp) == "already_resolved"
    cur = resp.json()["detail"]["current"]
    assert cur["active_party"] is None
    assert cur["proposal"]["state"] == "EXPIRED" and cur["proposal"]["party_id"] is None
    blob = json.dumps(resp.json())
    assert "Carol Example" not in blob and "+910000000003" not in blob
    assert "carol@example.test" not in blob and "alice@example.test" not in blob
    assert "transport_responsibility" not in blob and f'"party_id": {party_id}' not in blob
    # dave cannot read the party either
    assert world.client.get(f"{API}/parties/{party_id}", headers=world.headers["dave"]).status_code == 404


# ============================================================ idempotency
def test_accept_replay_returns_stored_result_without_side_effects(world):
    p = world.pair("alice", "bob")
    pid = p.proposal["id"]
    first = world.accept("bob", pid, 1, key="same")
    second = world.accept("bob", pid, 1, key="same")  # even with the version that is now stale
    third = world.client.post(f"{API}/connections/{pid}/accept", headers=world.headers["bob"],
                              json={"expected_version": 99, "idempotency_key": "same"})
    assert first.status_code == second.status_code == third.status_code == 200
    assert second.json() == first.json() == third.json()
    assert "idempotent-replay" not in first.headers
    assert second.headers["Idempotent-Replay"] == "true"
    assert len(world.rows(cm.TravelParty)) == 1
    assert len(world.events(first.json()["party"]["id"])) == 1
    assert len(world.rows(cm.IdempotencyRecord)) == 1


def test_accept_replay_while_agreed_keeps_contacts_for_the_acceptor_only(world):
    p = world.pair("alice", "bob")
    first = world.accept("bob", p.proposal["id"], 1, key="K")
    again = world.accept("bob", p.proposal["id"], 1, key="K")
    assert again.status_code == 200 and again.json() == first.json()
    assert again.json()["party"]["partner"]["phone_number"] == "+910000000001"
    # a DIFFERENT user replaying bob's key finds nothing: normal handling, no leakage
    for who in ("alice", "carol"):
        r = world.client.post(f"{API}/connections/{p.proposal['id']}/accept",
                              headers=world.headers[who],
                              json={"expected_version": 1, "idempotency_key": "K"})
        assert r.status_code == 404 and "party" not in r.json()
        assert "+91000" not in r.text and "@example.test" not in r.text


def test_accept_replay_after_party_ended_rebuilds_view_without_contacts(world):
    p = world.pair("alice", "bob")
    first = world.accept("bob", p.proposal["id"], 1, key="K")
    assert first.json()["party"]["partner"]["phone_number"] == "+910000000001"
    pid = first.json()["party"]["id"]
    assert world.client.post(f"{API}/parties/{pid}/cancel", headers=world.headers["alice"],
                             json={"idempotency_key": "c"}).status_code == 200
    again = world.accept("bob", p.proposal["id"], 1, key="K")
    assert again.status_code == 200  # same status, still a replay ...
    assert again.headers["Idempotent-Replay"] == "true"
    body = again.json()
    assert body["party"]["state"] == "CANCELLED"  # ... but built from CURRENT state
    assert body["party"]["partner"]["phone_number"] is None
    assert body["party"]["partner"]["email"] is None
    assert body["party"]["partner"]["full_name"] == "Alice Example"
    assert "+910000000001" not in again.text and "alice@example.test" not in again.text
    assert body["connection"]["state"] == "ACCEPTED"
    assert len(world.rows(cm.TravelParty)) == 1
    assert len(world.events(pid, "PARTY_AGREED")) == 1


def test_stored_body_has_contacts_but_a_late_replay_never_does(world):
    """The stored 2xx body contains contacts (as returned at the time); a replay after
    the party ended is rebuilt from live state instead."""
    p = world.pair("alice", "bob")
    first = world.accept("bob", p.proposal["id"], 1, key="K")
    pid = first.json()["party"]["id"]
    world.client.post(f"{API}/parties/{pid}/cancel", headers=world.headers["alice"],
                      json={"idempotency_key": "c"})
    db = world.sf()
    rec = db.query(cm.IdempotencyRecord).filter_by(operation="accept_connection").one()
    stored = json.loads(json.dumps(rec.response_body))
    assert stored["party"]["partner"]["phone_number"] == "+910000000001"  # as stored at the time
    db.close()
    again = world.accept("bob", p.proposal["id"], 1, key="K")
    assert "+910000000001" not in again.text


def test_idempotency_key_reused_for_another_proposal_is_422(world):
    ra, rb, rc = world.new_request("alice"), world.new_request("bob"), world.new_request("carol")
    rb2 = world.new_request("bob", 200, 300)
    rd = world.new_request("dave", 200, 300)
    p1 = world.propose("alice", world.suggestion(ra, rb)).json()
    p2 = world.propose("dave", world.suggestion(rd, rb2)).json()
    assert world.accept("bob", p1["id"], 1, key="shared").status_code == 200
    resp = world.accept("bob", p2["id"], 1, key="shared")
    assert resp.status_code == 422 and code(resp) == "idempotency_key_reused"
    assert len(world.rows(cm.TravelParty)) == 1
    # another user may use the same key string freely
    assert world.client.post(f"{API}/connections/{p2['id']}/accept", headers=world.headers["bob"],
                             json={"expected_version": 1, "idempotency_key": "other"}).status_code == 409


def test_failed_accept_is_not_stored_and_can_be_retried(world):
    p = world.pair("alice", "bob")
    assert world.accept("bob", p.proposal["id"], 5, key="retry").status_code == 409
    assert world.rows(cm.IdempotencyRecord) == []
    assert world.accept("bob", p.proposal["id"], 1, key="retry").status_code == 200


def test_integrity_error_from_partial_unique_index_becomes_clean_409(world, monkeypatch):
    """Both pre-checks pass (simulated race); the DB-level unique index still
    stops a second active party for alice and the result is a clean 409."""
    r1, r2 = world.new_request("alice", 10, 120), world.new_request("alice", 200, 300)
    rb, rc = world.new_request("bob", 10, 120), world.new_request("carol", 200, 300)
    p1 = world.propose("bob", world.suggestion(r1, rb)).json()
    p2 = world.propose("carol", world.suggestion(r2, rc)).json()
    assert world.accept("alice", p1["id"], 1, key="a").status_code == 200
    monkeypatch.setattr(svc, "_precheck_busy", lambda db, ids: [])  # pre-check blind
    resp = world.accept("alice", p2["id"], 1, key="b")
    assert resp.status_code == 409 and code(resp) == "participant_busy"
    assert resp.json()["detail"]["current"]["proposal"]["state"] == "PENDING"
    assert len(world.rows(cm.TravelParty)) == 1
    assert len(world.rows(cm.PartyMember)) == 2
    assert world.get(cm.TravelRequest, rc.id).status == RS.OPEN
    assert world.get(cm.TravelRequest, r2.id).status == RS.OPEN
    assert world.get(cm.ConnectionProposal, p2["id"]).state == PS.PENDING
    assert [r.key for r in world.rows(cm.IdempotencyRecord)] == ["a"]


# =========================================================== decline / withdraw
def test_decline_and_withdraw_flow(world):
    p = world.pair("alice", "bob")
    pid = p.proposal["id"]
    post = lambda who, action, body=None: world.client.post(  # noqa: E731
        f"{API}/connections/{pid}/{action}", headers=world.headers[who], json=body or {})
    # wrong role / third parties get 404
    assert post("alice", "decline").status_code == 404
    assert post("bob", "withdraw").status_code == 404
    assert post("carol", "decline").status_code == 404
    assert post("carol", "withdraw").status_code == 404
    # stale expected version
    r = post("bob", "decline", {"expected_version": 9})
    assert r.status_code == 409 and code(r) == "stale_version"

    first = post("bob", "decline")
    assert first.status_code == 200 and first.json()["state"] == "DECLINED"
    assert first.json()["direction"] == "incoming"
    again = post("bob", "decline")  # idempotent
    assert again.status_code == 200 and again.json() == first.json()
    row = world.get(cm.ConnectionProposal, pid)
    assert row.version == 2 and row.resolved_at is not None
    # not the opposite terminal state
    r = post("alice", "withdraw")
    assert r.status_code == 409 and code(r) == "already_resolved"
    # requests untouched; the pair can be proposed again
    assert world.get(cm.TravelRequest, p.ra.id).status == RS.OPEN
    assert world.propose("bob", p.suggestion_id).status_code == 201


def test_withdraw_by_proposer_is_idempotent_and_blocks_accept(world):
    p = world.pair("alice", "bob")
    pid = p.proposal["id"]
    url = f"{API}/connections/{pid}/withdraw"
    one = world.client.post(url, headers=world.headers["alice"], json={})
    two = world.client.post(url, headers=world.headers["alice"], json={})
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    assert one.json()["state"] == "WITHDRAWN" and one.json()["direction"] == "outgoing"
    resp = world.accept("bob", pid, 2)
    assert resp.status_code == 409 and code(resp) == "already_resolved"
    assert world.rows(cm.TravelParty) == []


def test_decline_notifies_proposer_and_survives_dead_socket(world, ws_delivery):
    p = world.pair("alice", "bob")
    ws_delivery.sent.clear()
    r = world.client.post(f"{API}/connections/{p.proposal['id']}/decline",
                          headers=world.headers["bob"], json={})
    assert r.status_code == 200
    assert [(u, m["type"]) for u, m in ws_delivery.sent] == [
        (world.users["alice"].id, "connection_declined")]
    ws_delivery.fail_all()
    p2 = world.pair("carol", "dave")
    r = world.client.post(f"{API}/connections/{p2.proposal['id']}/withdraw",
                          headers=world.headers["carol"], json={})
    assert r.status_code == 200


def test_decline_expired_proposal_reports_expired(world):
    p = world.pair("alice", "bob")
    world.clock.advance(minutes=45)
    r = world.client.post(f"{API}/connections/{p.proposal['id']}/decline",
                          headers=world.headers["bob"], json={})
    assert r.status_code == 409 and code(r) == "expired"
    assert world.get(cm.ConnectionProposal, p.proposal["id"]).state == PS.EXPIRED


# ============================================ deadlock hardening / robustness
@pytest.mark.parametrize("proposer,recipient", [("bob", "alice"), ("alice", "bob")])
def test_party_members_are_inserted_in_ascending_user_id_order(world, proposer, recipient):
    p = world.pair(proposer, recipient)
    resp = world.accept(recipient, p.proposal["id"], 1)
    assert resp.status_code == 200
    db = world.sf()
    try:
        rows = (db.query(cm.PartyMember).filter_by(party_id=resp.json()["party"]["id"])
                .order_by(cm.PartyMember.id).all())
    finally:
        db.close()
    ids = [m.user_id for m in rows]
    assert ids == sorted(ids) and len(ids) == 2


def test_accept_retries_once_after_a_deadlock_style_operational_error(world, monkeypatch):
    from sqlalchemy.exc import OperationalError

    p = world.pair("alice", "bob")
    real, calls = svc._lock_users, []

    def flaky(db, ids):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("SELECT ...", {}, Exception("deadlock detected"))
        return real(db, ids)

    monkeypatch.setattr(svc, "_lock_users", flaky)
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 200 and len(calls) == 2
    assert len(world.rows(cm.TravelParty)) == 1


def test_accept_gives_a_clean_409_when_the_deadlock_persists(world, monkeypatch):
    from sqlalchemy.exc import OperationalError

    p = world.pair("alice", "bob")

    def always(db, ids):
        raise OperationalError("SELECT ...", {}, Exception("deadlock detected"))

    monkeypatch.setattr(svc, "_lock_users", always)
    resp = world.accept("bob", p.proposal["id"], 1)
    assert resp.status_code == 409 and code(resp) == "participant_busy"
    assert resp.json()["detail"]["current"]["proposal"]["state"] == "PENDING"
    assert world.rows(cm.TravelParty) == []


def test_list_connections_limit_and_no_n_plus_one(world, test_engine):
    for _ in range(4):
        world.pair("alice", "bob")
    h = world.headers["alice"]
    assert len(world.client.get(f"{API}/connections", headers=h).json()) == 4
    assert len(world.client.get(f"{API}/connections?limit=2", headers=h).json()) == 2
    assert world.client.get(f"{API}/connections?limit=0", headers=h).status_code == 422
    assert world.client.get(f"{API}/connections?limit=201", headers=h).status_code == 422

    def count_for(n):
        statements = []

        def spy(conn, cursor, statement, *a):
            statements.append(statement)
        event.listen(test_engine, "before_cursor_execute", spy)
        try:
            assert len(world.client.get(f"{API}/connections?limit={n}", headers=h).json()) == n
        finally:
            event.remove(test_engine, "before_cursor_execute", spy)
        return len(statements)

    assert count_for(4) == count_for(1)  # statement count does not grow with the rows


def test_absurd_ids_are_422_not_500(world):
    big = 10 ** 25
    h = world.headers["alice"]
    assert world.client.get(f"{API}/parties/{big}", headers=h).status_code == 422
    assert world.client.post(f"{API}/suggestions/{big}/connections", headers=h, json={}).status_code == 422
    assert world.client.post(f"{API}/connections/{big}/accept", headers=h,
                             json={"expected_version": 1, "idempotency_key": "k"}).status_code == 422


# ====================================================== threaded races (SQLite)
@pytest.fixture(params=["plain", "begin_immediate"])
def file_db(request, tmp_path):
    """A file-backed SQLite database with real concurrent connections.

    plain: default pysqlite behaviour (writers serialize on the file lock, so the
    losers are stopped by the re-read checks or the partial unique indexes).
    begin_immediate: every transaction takes the write lock up front, emulating
    SELECT ... FOR UPDATE serialization.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    if request.param == "begin_immediate":
        @event.listens_for(engine, "connect")
        def _no_driver_begin(dbapi_connection, _):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def _begin_immediate(conn):
            conn.exec_driver_sql("BEGIN IMMEDIATE")
    Base.metadata.create_all(bind=engine)
    sf = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield sf
    engine.dispose()


def _accept_job(proposal_id, user_id, key):
    body = schemas.ConnectionAccept(expected_version=1, idempotency_key=key)

    def job(db):
        return svc.accept_proposal(db, db.get(user_model.User, user_id), proposal_id, body)
    return job


def _assert_single_winner(sf, outcomes, details, *, winner_pair_requests, loser_request):
    assert sorted(outcomes, key=str) == [200, 409], (outcomes, details)
    assert details[outcomes.index(409)]["code"] in ("already_resolved", "participant_busy")
    db = sf()
    try:
        parties = db.query(cm.TravelParty).all()
        assert len(parties) == 1 and parties[0].state == cm.PartyState.AGREED
        assert db.query(cm.PartyMember).filter_by(active=True).count() == 2
        assert [e.event_type for e in db.query(cm.PartyEvent).all()] == ["PARTY_AGREED"]
        for rid in winner_pair_requests:
            assert db.get(cm.TravelRequest, rid).status == RS.RESERVED
        assert db.get(cm.TravelRequest, loser_request).status == RS.OPEN
        states = sorted(p.state.value for p in db.query(cm.ConnectionProposal).all())
        assert states == ["ACCEPTED", "EXPIRED"]
        assert db.query(cm.IdempotencyRecord).count() == 1
    finally:
        db.close()


def test_threaded_concurrent_accepts_by_one_student(file_db, clock):
    """bob receives proposals from alice and carol and accepts both at once."""
    ids = seed_college(file_db)
    now = clock.now
    u = {k: seed_user(file_db, ids["college_id"], k) for k in ("alice", "bob", "carol")}
    r = {k: seed_request(file_db, ids, u[k], now) for k in u}
    p_a = seed_proposal(file_db, u["alice"], u["bob"], r["alice"], r["bob"], now)
    p_c = seed_proposal(file_db, u["carol"], u["bob"], r["carol"], r["bob"], now)
    outcomes, details = race(file_db, [_accept_job(p_a, u["bob"], "k-a"),
                                       _accept_job(p_c, u["bob"], "k-c")])
    db = file_db()
    winner = db.query(cm.ConnectionProposal).filter_by(state=PS.ACCEPTED).one()
    db.close()
    win_req = winner.proposer_request_id
    loser_req = r["carol"] if win_req == r["alice"] else r["alice"]
    _assert_single_winner(file_db, outcomes, details,
                          winner_pair_requests=[win_req, r["bob"]], loser_request=loser_req)


def test_threaded_concurrent_accepts_by_two_students_competing_for_one(file_db, clock):
    """carol -> alice (alice accepts) vs alice -> dave (dave accepts) at the same time."""
    ids = seed_college(file_db)
    now = clock.now
    u = {k: seed_user(file_db, ids["college_id"], k) for k in ("alice", "carol", "dave")}
    r = {k: seed_request(file_db, ids, u[k], now) for k in u}
    p_ca = seed_proposal(file_db, u["carol"], u["alice"], r["carol"], r["alice"], now)
    p_ad = seed_proposal(file_db, u["alice"], u["dave"], r["alice"], r["dave"], now)
    outcomes, details = race(file_db, [_accept_job(p_ca, u["alice"], "k1"),
                                       _accept_job(p_ad, u["dave"], "k2")])
    winner_other = r["carol"] if outcomes[0] == 200 else r["dave"]
    loser_req = r["dave"] if outcomes[0] == 200 else r["carol"]
    _assert_single_winner(file_db, outcomes, details,
                          winner_pair_requests=[r["alice"], winner_other], loser_request=loser_req)
    # the loser's 409 carries no party information
    loser_detail = details[outcomes.index(409)]
    if outcomes[1] == 409:  # dave lost: not a member of the winning party
        assert loser_detail["current"]["active_party"] is None


def test_threaded_same_key_accepts_replay_instead_of_conflicting(file_db, clock):
    ids = seed_college(file_db)
    now = clock.now
    u = {k: seed_user(file_db, ids["college_id"], k) for k in ("alice", "bob")}
    r = {k: seed_request(file_db, ids, u[k], now) for k in u}
    pid = seed_proposal(file_db, u["alice"], u["bob"], r["alice"], r["bob"], now)
    outcomes, _ = race(file_db, [_accept_job(pid, u["bob"], "dup"), _accept_job(pid, u["bob"], "dup")])
    assert outcomes == [200, 200]  # second is a replay of the first
    db = file_db()
    try:
        assert db.query(cm.TravelParty).count() == 1
        assert db.query(cm.PartyEvent).count() == 1
        assert db.query(cm.IdempotencyRecord).count() == 1
    finally:
        db.close()


def test_threaded_both_members_cancel_simultaneously(file_db, clock):
    ids = seed_college(file_db)
    now = clock.now
    u = {k: seed_user(file_db, ids["college_id"], k) for k in ("alice", "bob")}
    r = {k: seed_request(file_db, ids, u[k], now) for k in u}
    party_id = seed_party(file_db, ids, [u["alice"], u["bob"]], [r["alice"], r["bob"]], now)

    def cancel_job(uid, key):
        body = schemas.PartyCancel(idempotency_key=key)

        def job(db):
            return svc.cancel_party(db, db.get(user_model.User, uid), party_id, body)
        return job

    outcomes, details = race(file_db, [cancel_job(u["alice"], "ka"), cancel_job(u["bob"], "kb")])
    assert outcomes == [200, 200], (outcomes, details)
    db = file_db()
    try:
        assert db.get(cm.TravelParty, party_id).state == cm.PartyState.CANCELLED
        events = db.query(cm.PartyEvent).filter_by(party_id=party_id).order_by(cm.PartyEvent.version).all()
        assert [e.event_type for e in events] == ["PARTY_AGREED", "PARTY_CANCELLED"]
        actor = events[-1].actor_id
        statuses = {uid: db.get(cm.TravelRequest, r[k]).status for k, uid in u.items()}
        assert statuses[actor] == RS.CANCELLED
        assert [s for uid, s in statuses.items() if uid != actor] == [RS.OPEN]
        assert db.query(cm.OutboxMessage).filter_by(event_id=events[-1].id).count() == 2
    finally:
        db.close()
