"""Parties: view, cancel, change proposals, cost note, outcome reports. Fictional data only."""

import json
from datetime import timedelta

import pytest

from app.models import campus_model as cm
from app.models import user_model
from app.core import campus_time
from tests.campus_party_helpers import API, world  # noqa: F401  (world is a fixture)

RS = cm.TravelRequestStatus
PS = cm.PartyState


def code(resp):
    return resp.json()["detail"]["code"]


def iso(dt):
    return dt.isoformat()


@pytest.fixture
def party(world):
    return world.party("alice", "bob")


def url(party_id, suffix=""):
    return f"{API}/parties/{party_id}{suffix}"


def cancel(world, who, party_id, key="c1", **body):
    return world.client.post(url(party_id, "/cancel"), headers=world.headers[who],
                             json={"idempotency_key": key, **body})


def get_party(world, who, party_id):
    return world.client.get(url(party_id), headers=world.headers[who])


def propose_change(world, who, party_id, version, **body):
    return world.client.post(url(party_id, "/changes"), headers=world.headers[who],
                             json={"expected_version": version, **body})


def decide(world, who, party_id, change_id, action, **body):
    return world.client.post(url(party_id, f"/changes/{change_id}/{action}"),
                             headers=world.headers[who], json=body)


def report(world, who, party_id, outcome):
    return world.client.post(url(party_id, "/report"), headers=world.headers[who],
                             json={"outcome": outcome})


def start_trip(world):
    """Move the fake clock past the agreed departure (party departs at now+10)."""
    world.clock.advance(minutes=11)


# ================================================================ viewing
def test_members_can_view_and_third_users_get_404(world, party):
    for who in ("alice", "bob"):
        resp = get_party(world, who, party.id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == party.id and body["state"] == "AGREED" and body["version"] == 1
        other = "bob" if who == "alice" else "alice"
        assert body["partner"]["user_id"] == world.users[other].id
        assert body["partner"]["phone_number"] == f"+91000000000{1 if other == 'alice' else 2}"
        assert body["partner"]["email"] == f"{other}@example.test"
        assert body["pending_change"] is None
    assert get_party(world, "carol", party.id).status_code == 404
    assert world.client.get(url(99999), headers=world.headers["alice"]).status_code == 404
    assert world.client.get(url(party.id)).status_code == 401


def test_third_user_is_locked_out_of_every_party_endpoint(world, party):
    c = world.headers["carol"]
    post = lambda path, body: world.client.post(url(party.id, path), headers=c, json=body)  # noqa: E731
    assert post("/cancel", {"idempotency_key": "k"}).status_code == 404
    assert post("/changes", {"expected_version": 1, "note": "x"}).status_code == 404
    assert post("/report", {"outcome": "COMPLETED"}).status_code == 404
    assert post("/changes/1/approve", {"expected_party_version": 1}).status_code == 404
    assert post("/changes/1/reject", {}).status_code == 404
    assert post("/changes/1/withdraw", {}).status_code == 404
    assert world.client.patch(url(party.id), headers=c,
                              json={"expected_version": 1, "cost_note": "x"}).status_code == 404
    # nothing changed
    assert world.get(cm.TravelParty, party.id).version == 1
    assert len(world.events(party.id)) == 1


# ================================================================== cancel
@pytest.mark.parametrize("canceller,partner", [("alice", "bob"), ("bob", "alice")])
def test_cancel_by_either_member_is_one_transaction(world, party, canceller, partner):
    my_req, other_req = (party.ra, party.rb) if canceller == "alice" else (party.rb, party.ra)
    resp = cancel(world, canceller, party.id, reason="plans changed")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "CANCELLED" and body["version"] == 2
    assert body["end_reason"] == "cancelled_by_member" and body["ended_at"]
    # contact fields are gone once the party ended; the name stays
    assert body["partner"]["full_name"] == f"{partner.title()} Example"
    assert body["partner"]["phone_number"] is None and body["partner"]["email"] is None

    row = world.get(cm.TravelParty, party.id)
    assert row.state == PS.CANCELLED and row.ended_at is not None
    assert all(not m.active for m in world.rows(cm.PartyMember, party_id=party.id))
    mine, theirs = world.get(cm.TravelRequest, my_req.id), world.get(cm.TravelRequest, other_req.id)
    assert mine.status == RS.CANCELLED and mine.version == 3
    assert theirs.status == RS.OPEN and theirs.version == 3  # reopened, NOT re-matched

    events = world.events(party.id, "PARTY_CANCELLED")
    assert len(events) == 1 and events[0].version == 2
    assert events[0].actor_id == world.users[canceller].id
    assert events[0].payload["reason"] == "plans changed"
    outbox = [o for o in world.rows(cm.OutboxMessage) if o.event_id == events[0].id]
    assert sorted(o.recipient_id for o in outbox) == sorted(
        [world.users["alice"].id, world.users["bob"].id])
    # both views agree
    assert get_party(world, partner, party.id).json()["partner"]["phone_number"] is None
    # the freed students may now start over: no active membership remains
    assert world.rows(cm.PartyMember, active=True) == []


def test_cancel_commits_even_when_notification_delivery_fails(world, party, ws_delivery):
    ws_delivery.fail_all()
    resp = cancel(world, "alice", party.id)
    assert resp.status_code == 200 and resp.json()["state"] == "CANCELLED"
    assert world.get(cm.TravelParty, party.id).state == PS.CANCELLED
    event = world.events(party.id, "PARTY_CANCELLED")[0]
    rows = [o for o in world.rows(cm.OutboxMessage) if o.event_id == event.id]
    assert len(rows) == 2 and all(o.status == cm.OutboxStatus.PENDING for o in rows)


def test_cancel_commits_even_when_dispatch_raises(world, party, monkeypatch):
    from app.services import campus_outbox

    async def boom(db, party_id):
        raise RuntimeError("down")

    monkeypatch.setattr(campus_outbox, "dispatch_for_party", boom)
    resp = cancel(world, "bob", party.id)
    assert resp.status_code == 200
    assert world.get(cm.TravelParty, party.id).state == PS.CANCELLED
    assert len(world.events(party.id, "PARTY_CANCELLED")) == 1


def test_cancel_dispatch_happens_after_commit(world, party, monkeypatch):
    from app.services import campus_outbox

    seen = []

    async def spy(db, party_id):
        seen.append(world.get(cm.TravelParty, party_id).state)
        return 0

    monkeypatch.setattr(campus_outbox, "dispatch_for_party", spy)
    cancel(world, "alice", party.id)
    assert seen == [PS.CANCELLED]


def test_cancel_replay_with_lost_response_creates_one_event(world, party, ws_delivery):
    ws_delivery.fail_all()
    first = cancel(world, "alice", party.id, key="retry-me")
    again = cancel(world, "alice", party.id, key="retry-me")  # the response was "lost"
    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replay"] == "true"
    assert "idempotent-replay" not in first.headers
    assert len(world.events(party.id, "PARTY_CANCELLED")) == 1
    assert world.get(cm.TravelParty, party.id).version == 2
    assert len(world.rows(cm.IdempotencyRecord, operation="cancel_party")) == 1


def test_cancel_of_already_cancelled_party_is_idempotent_for_both_members(world, party):
    assert cancel(world, "alice", party.id, key="a").status_code == 200
    other_key = cancel(world, "alice", party.id, key="b")
    partner = cancel(world, "bob", party.id, key="c")
    assert other_key.status_code == partner.status_code == 200
    assert other_key.json()["state"] == "CANCELLED" and partner.json()["state"] == "CANCELLED"
    assert "idempotent-replay" not in partner.headers
    assert len(world.events(party.id, "PARTY_CANCELLED")) == 1
    assert world.get(cm.TravelParty, party.id).version == 2
    # bob's request was not touched by his no-op cancel
    assert world.get(cm.TravelRequest, party.rb.id).status == RS.OPEN


def test_cancel_key_reused_for_a_different_party_is_422(world):
    first = world.party("alice", "bob")
    assert cancel(world, "alice", first.id, key="same").status_code == 200
    second = world.party("alice", "carol")
    resp = cancel(world, "alice", second.id, key="same")
    assert resp.status_code == 422 and code(resp) == "idempotency_key_reused"
    assert world.get(cm.TravelParty, second.id).state == PS.AGREED


def test_cancel_partner_request_reopens_while_window_open_else_expires(world):
    long_party = world.party("alice", "bob", start=10, end=300)
    short_party = world.party("carol", "dave", start=10, end=60)
    world.clock.advance(minutes=90)  # past dave/carol's window, inside alice/bob's
    assert cancel(world, "alice", long_party.id, key="x").status_code == 200
    assert cancel(world, "carol", short_party.id, key="y").status_code == 200
    assert world.get(cm.TravelRequest, long_party.ra.id).status == RS.CANCELLED
    assert world.get(cm.TravelRequest, long_party.rb.id).status == RS.OPEN
    assert world.get(cm.TravelRequest, short_party.ra.id).status == RS.CANCELLED
    assert world.get(cm.TravelRequest, short_party.rb.id).status == RS.EXPIRED


def test_cancel_rejected_for_finished_parties(world, party):
    start_trip(world)
    report(world, "alice", party.id, "COMPLETED")
    report(world, "bob", party.id, "COMPLETED")
    resp = cancel(world, "alice", party.id)
    assert resp.status_code == 409 and code(resp) == "party_not_cancellable"
    assert resp.json()["detail"]["current"]["party"]["state"] == "COMPLETED"

    other = world.party("carol", "dave")
    start_trip(world)
    report(world, "carol", other.id, "COMPLETED")
    report(world, "dave", other.id, "DID_NOT_HAPPEN")
    resp = cancel(world, "carol", other.id)
    assert resp.status_code == 409 and code(resp) == "party_not_cancellable"
    assert world.get(cm.TravelParty, other.id).state == PS.DISPUTED


def test_cancel_with_stale_expected_version(world, party):
    resp = cancel(world, "alice", party.id, expected_version=5)
    assert resp.status_code == 409 and code(resp) == "stale_version"
    assert world.get(cm.TravelParty, party.id).state == PS.AGREED
    assert cancel(world, "alice", party.id, key="ok", expected_version=1).status_code == 200


def test_cancel_supersedes_pending_change(world, party):
    ch = propose_change(world, "bob", party.id, 1, note="later?",
                        agreed_departure=iso(world.clock.now + timedelta(minutes=60))).json()
    assert cancel(world, "alice", party.id).status_code == 200
    row = world.get(cm.PartyChangeProposal, ch["id"])
    assert row.state == cm.ChangeState.SUPERSEDED and row.resolved_at is not None
    resp = decide(world, "alice", party.id, ch["id"], "approve", expected_party_version=3)
    assert resp.status_code == 409 and code(resp) == "change_not_pending"


# ================================================================== changes
def test_change_needs_the_other_members_approval(world, party):
    new_dep = world.clock.now + timedelta(minutes=45)
    original = world.get(cm.TravelParty, party.id).agreed_departure
    resp = propose_change(world, "bob", party.id, 1, agreed_departure=iso(new_dep), note="bus is late")
    assert resp.status_code == 201, resp.text
    ch = resp.json()
    assert ch["state"] == "PENDING" and ch["proposer_id"] == world.users["bob"].id
    assert ch["new_departure"]["utc"].startswith(new_dep.strftime("%Y-%m-%dT%H:%M"))

    # party values are unchanged; both members see the pending change
    row = world.get(cm.TravelParty, party.id)
    assert row.agreed_departure == original and row.version == 2
    for who in ("alice", "bob"):
        assert get_party(world, who, party.id).json()["pending_change"]["id"] == ch["id"]
    assert [e.event_type for e in world.events(party.id)] == ["PARTY_AGREED", "CHANGE_PROPOSED"]

    # the proposer cannot approve (or reject) their own change
    own = decide(world, "bob", party.id, ch["id"], "approve", expected_party_version=2)
    assert own.status_code == 403
    assert decide(world, "bob", party.id, ch["id"], "reject").status_code == 403
    assert world.get(cm.TravelParty, party.id).agreed_departure == original

    # stale version
    stale = decide(world, "alice", party.id, ch["id"], "approve", expected_party_version=1)
    assert stale.status_code == 409 and code(stale) == "stale_version"
    assert world.get(cm.TravelParty, party.id).agreed_departure == original

    ok = decide(world, "alice", party.id, ch["id"], "approve", expected_party_version=2)
    assert ok.status_code == 200, ok.text
    view = ok.json()
    assert view["version"] == 3 and view["pending_change"] is None
    assert campus_time.from_db(world.get(cm.TravelParty, party.id).agreed_departure) == new_dep
    assert view["agreed_departure"]["utc"].startswith(new_dep.strftime("%Y-%m-%dT%H:%M"))
    assert world.get(cm.PartyChangeProposal, ch["id"]).state == cm.ChangeState.APPROVED
    assert world.get(cm.PartyChangeProposal, ch["id"]).resolved_by == world.users["alice"].id
    assert [e.event_type for e in world.events(party.id)][-1] == "PARTY_CHANGED"
    # approving again is a clean 409
    again = decide(world, "alice", party.id, ch["id"], "approve", expected_party_version=3)
    assert again.status_code == 409 and code(again) == "change_not_pending"


def test_change_meeting_point_applies_only_on_approval(world, party):
    campus2 = world.landmarks["campus2"]
    ch = propose_change(world, "alice", party.id, 1, meeting_landmark_id=campus2.id).json()
    assert ch["new_meeting_landmark"]["id"] == campus2.id
    assert world.get(cm.TravelParty, party.id).meeting_landmark_id == world.landmarks["campus"].id
    ok = decide(world, "bob", party.id, ch["id"], "approve", expected_party_version=2)
    assert ok.status_code == 200
    assert ok.json()["meeting_landmark"]["id"] == campus2.id
    assert world.get(cm.TravelParty, party.id).meeting_landmark_id == campus2.id


def test_reject_leaves_party_unchanged_and_emits_event(world, party):
    original = world.get(cm.TravelParty, party.id).agreed_departure
    ch = propose_change(world, "alice", party.id, 1,
                        agreed_departure=iso(world.clock.now + timedelta(minutes=50))).json()
    resp = decide(world, "bob", party.id, ch["id"], "reject")
    assert resp.status_code == 200 and resp.json()["state"] == "REJECTED"
    row = world.get(cm.TravelParty, party.id)
    assert row.agreed_departure == original and row.version == 3
    assert world.events(party.id)[-1].event_type == "CHANGE_REJECTED"
    assert get_party(world, "alice", party.id).json()["pending_change"] is None
    # a new proposal is possible again
    assert propose_change(world, "bob", party.id, 3, note="x",
                          agreed_departure=iso(world.clock.now + timedelta(minutes=55))).status_code == 201


def test_proposer_can_withdraw_but_the_other_member_cannot(world, party):
    ch = propose_change(world, "alice", party.id, 1,
                        agreed_departure=iso(world.clock.now + timedelta(minutes=50))).json()
    assert decide(world, "bob", party.id, ch["id"], "withdraw").status_code == 403
    resp = decide(world, "alice", party.id, ch["id"], "withdraw")
    assert resp.status_code == 200 and resp.json()["state"] == "WITHDRAWN"
    assert get_party(world, "bob", party.id).json()["pending_change"] is None
    last = world.events(party.id)[-1]
    assert last.event_type == "CHANGE_REJECTED" and last.payload["withdrawn"] is True
    assert decide(world, "alice", party.id, ch["id"], "withdraw").status_code == 409


def test_only_one_pending_change_at_a_time(world, party):
    dep = iso(world.clock.now + timedelta(minutes=50))
    first = propose_change(world, "alice", party.id, 1, agreed_departure=dep)
    assert first.status_code == 201
    for who in ("alice", "bob"):
        resp = propose_change(world, who, party.id, 2, agreed_departure=dep)
        assert resp.status_code == 409 and code(resp) == "change_pending"
        assert resp.json()["detail"]["current"]["party"]["pending_change"]["id"] == first.json()["id"]
    assert len(world.rows(cm.PartyChangeProposal)) == 1


def test_change_validation(world, party):
    now = world.clock.now
    assert propose_change(world, "alice", party.id, 1).status_code == 422                # nothing proposed
    assert propose_change(world, "alice", party.id, 1, note="only a note").status_code == 422
    past = propose_change(world, "alice", party.id, 1, agreed_departure=iso(now - timedelta(minutes=1)))
    assert past.status_code == 422 and code(past) == "departure_in_past"
    naive = propose_change(world, "alice", party.id, 1, agreed_departure="2026-03-01T10:00:00")
    assert naive.status_code == 422
    stale = propose_change(world, "alice", party.id, 9, agreed_departure=iso(now + timedelta(hours=1)))
    assert stale.status_code == 409 and code(stale) == "stale_version"
    assert world.rows(cm.PartyChangeProposal) == []


def test_material_change_landmark_must_be_active_campus_point_of_same_college(world, party, test_session_factory):
    db = test_session_factory()
    other_college = user_model.College(name="Other College")
    db.add(other_college)
    db.flush()
    foreign = cm.CampusLandmark(college_id=other_college.id, name="Foreign Gate",
                                kind=cm.LandmarkKind.CAMPUS_POINT, latitude=1.0, longitude=1.0,
                                timezone="Asia/Kolkata", active=True)
    inactive = cm.CampusLandmark(college_id=world.college.id, name="Closed Gate",
                                 kind=cm.LandmarkKind.CAMPUS_POINT, latitude=1.0, longitude=1.0,
                                 timezone="Asia/Kolkata", active=False)
    db.add_all([foreign, inactive])
    db.commit()
    foreign_id, inactive_id = foreign.id, inactive.id
    db.close()
    for bad in (world.landmarks["hub"].id, foreign_id, inactive_id, 424242):
        resp = propose_change(world, "alice", party.id, 1, meeting_landmark_id=bad)
        assert resp.status_code == 422 and code(resp) == "invalid_landmark", bad
    assert world.rows(cm.PartyChangeProposal) == []
    assert world.get(cm.TravelParty, party.id).version == 1


def test_approval_rechecks_that_the_departure_is_still_in_the_future(world, party):
    ch = propose_change(world, "alice", party.id, 1,
                        agreed_departure=iso(world.clock.now + timedelta(minutes=30))).json()
    world.clock.advance(minutes=31)
    resp = decide(world, "bob", party.id, ch["id"], "approve", expected_party_version=2)
    assert resp.status_code == 409 and code(resp) == "change_no_longer_valid"
    assert world.get(cm.PartyChangeProposal, ch["id"]).state == cm.ChangeState.PENDING


def test_change_on_unknown_or_foreign_change_id(world, party):
    assert decide(world, "alice", party.id, 9999, "approve", expected_party_version=1).status_code == 404
    other = world.party("carol", "dave")
    ch = propose_change(world, "carol", other.id, 1,
                        agreed_departure=iso(world.clock.now + timedelta(minutes=40))).json()
    # a change id from another party is never reachable through this one
    assert decide(world, "bob", party.id, ch["id"], "approve", expected_party_version=2).status_code == 404


def test_changes_are_refused_once_the_party_ended(world, party):
    cancel(world, "alice", party.id)
    resp = propose_change(world, "bob", party.id, 2,
                          agreed_departure=iso(world.clock.now + timedelta(minutes=40)))
    assert resp.status_code == 409 and code(resp) == "party_not_active"


# =================================================================== note
def test_cost_note_patch(world, party):
    resp = world.client.patch(url(party.id), headers=world.headers["bob"],
                              json={"expected_version": 1, "cost_note": "split 50/50 on the meter"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["cost_note"] == "split 50/50 on the meter" and resp.json()["version"] == 2
    assert get_party(world, "alice", party.id).json()["cost_note"] == "split 50/50 on the meter"
    assert world.events(party.id)[-1].event_type == "NOTE_UPDATED"
    # no approval needed, nothing material moved
    assert world.get(cm.TravelParty, party.id).state == PS.AGREED
    # stale
    stale = world.client.patch(url(party.id), headers=world.headers["alice"],
                               json={"expected_version": 1, "cost_note": "x"})
    assert stale.status_code == 409 and code(stale) == "stale_version"
    assert world.get(cm.TravelParty, party.id).cost_note == "split 50/50 on the meter"
    # clear it
    cleared = world.client.patch(url(party.id), headers=world.headers["alice"],
                                 json={"expected_version": 2, "cost_note": None})
    assert cleared.status_code == 200 and cleared.json()["cost_note"] is None
    too_long = world.client.patch(url(party.id), headers=world.headers["alice"],
                                  json={"expected_version": 3, "cost_note": "x" * 501})
    assert too_long.status_code == 422


def test_cost_note_refused_after_the_party_ended(world, party):
    cancel(world, "alice", party.id)
    resp = world.client.patch(url(party.id), headers=world.headers["bob"],
                              json={"expected_version": 2, "cost_note": "late"})
    assert resp.status_code == 409 and code(resp) == "party_not_active"


# ================================================================= reports
def test_report_before_the_agreed_departure_is_rejected(world, party):
    resp = report(world, "alice", party.id, "COMPLETED")
    assert resp.status_code == 409 and code(resp) == "report_too_early"
    assert all(m.report_outcome is None for m in world.rows(cm.PartyMember, party_id=party.id))
    world.clock.advance(minutes=9, seconds=59)
    assert report(world, "alice", party.id, "COMPLETED").status_code == 409
    world.clock.advance(seconds=1)  # exactly at agreed_departure
    assert report(world, "alice", party.id, "COMPLETED").status_code == 200


def test_both_completed_completes_the_party(world, party):
    start_trip(world)
    first = report(world, "alice", party.id, "COMPLETED")
    assert first.status_code == 200 and first.json()["state"] == "AGREED"
    me = next(m for m in first.json()["members"] if m["you"])
    assert me["report_outcome"] == "COMPLETED"
    assert world.get(cm.TravelRequest, party.ra.id).status == RS.RESERVED

    second = report(world, "bob", party.id, "COMPLETED")
    assert second.status_code == 200
    body = second.json()
    assert body["state"] == "COMPLETED" and body["end_reason"] == "completed" and body["ended_at"]
    assert body["partner"]["phone_number"] is None and body["partner"]["email"] is None
    for r in (party.ra, party.rb):
        assert world.get(cm.TravelRequest, r.id).status == RS.FULFILLED
    assert all(not m.active for m in world.rows(cm.PartyMember, party_id=party.id))
    assert [e.event_type for e in world.events(party.id)] == [
        "PARTY_AGREED", "REPORT_RECORDED", "REPORT_RECORDED", "PARTY_COMPLETED"]
    assert world.get(cm.TravelParty, party.id).version == 4
    # retry of the final report is a harmless no-op; a different outcome is refused
    assert report(world, "bob", party.id, "COMPLETED").status_code == 200
    resp = report(world, "bob", party.id, "DID_NOT_HAPPEN")
    assert resp.status_code == 409 and code(resp) == "party_not_active"
    assert len(world.events(party.id)) == 4


def test_mixed_reports_dispute_the_party(world, party):
    start_trip(world)
    report(world, "alice", party.id, "COMPLETED")
    resp = report(world, "bob", party.id, "DID_NOT_HAPPEN")
    assert resp.status_code == 200 and resp.json()["state"] == "DISPUTED"
    assert resp.json()["end_reason"] == "disputed"
    for r in (party.ra, party.rb):
        assert world.get(cm.TravelRequest, r.id).status == RS.CANCELLED
    assert all(not m.active for m in world.rows(cm.PartyMember, party_id=party.id))
    assert world.events(party.id)[-1].event_type == "PARTY_DISPUTED"


def test_both_did_not_happen_cancels_the_party(world, party):
    start_trip(world)
    report(world, "alice", party.id, "DID_NOT_HAPPEN")
    resp = report(world, "bob", party.id, "DID_NOT_HAPPEN")
    assert resp.status_code == 200
    assert resp.json()["state"] == "CANCELLED" and resp.json()["end_reason"] == "did_not_happen"
    for r in (party.ra, party.rb):
        assert world.get(cm.TravelRequest, r.id).status == RS.CANCELLED
    assert world.events(party.id)[-1].event_type == "PARTY_CANCELLED"


def test_a_member_can_change_their_report_until_the_other_reports(world, party):
    start_trip(world)
    report(world, "alice", party.id, "DID_NOT_HAPPEN")
    again = report(world, "alice", party.id, "COMPLETED")
    assert again.status_code == 200 and again.json()["state"] == "AGREED"
    mine = next(m for m in again.json()["members"] if m["you"])
    assert mine["report_outcome"] == "COMPLETED"
    assert report(world, "bob", party.id, "COMPLETED").json()["state"] == "COMPLETED"


def test_report_validation_and_pending_change_is_superseded_when_party_ends(world, party):
    start_trip(world)
    assert report(world, "alice", party.id, "MAYBE").status_code == 422
    ch = propose_change(world, "alice", party.id, 1,
                        agreed_departure=iso(world.clock.now + timedelta(minutes=30))).json()
    report(world, "alice", party.id, "COMPLETED")
    report(world, "bob", party.id, "COMPLETED")
    assert world.get(cm.PartyChangeProposal, ch["id"]).state == cm.ChangeState.SUPERSEDED


def test_contact_fields_hidden_after_every_way_a_party_ends(world):
    for ending in ("cancel", "complete", "dispute"):
        a, b = {"cancel": ("alice", "bob"), "complete": ("carol", "dave"),
                "dispute": ("bob", "carol")}[ending]
        p = world.party(a, b)
        live = get_party(world, a, p.id).json()
        assert live["partner"]["email"] and live["partner"]["phone_number"]
        if ending == "cancel":
            cancel(world, a, p.id, key=f"end-{ending}")
        else:
            start_trip(world)
            report(world, a, p.id, "COMPLETED")
            report(world, b, p.id, "COMPLETED" if ending == "complete" else "DID_NOT_HAPPEN")
        for who in (a, b):
            ended = get_party(world, who, p.id)
            assert ended.status_code == 200
            blob = json.dumps(ended.json())
            assert "@example.test" not in blob and "+91000" not in blob
            assert ended.json()["partner"]["full_name"]
            assert ended.json()["state"] in ("CANCELLED", "COMPLETED", "DISPUTED")


# ============================================================ blind reporting
def members_by_user(body):
    return {m["user_id"]: m for m in body["members"]}


def test_partner_outcome_is_hidden_while_agreed(world, party):
    start_trip(world)
    a, b = world.users["alice"].id, world.users["bob"].id
    resp = report(world, "alice", party.id, "DID_NOT_HAPPEN")
    assert resp.status_code == 200
    mine = members_by_user(resp.json())
    assert mine[a]["report_outcome"] == "DID_NOT_HAPPEN" and mine[a]["reported"] is True
    assert mine[b]["report_outcome"] is None and mine[b]["reported"] is False

    for path in (url(party.id), f"{API}/events?party_id={party.id}"):
        body = world.client.get(path, headers=world.headers["bob"]).json()
        view = body.get("party", body)
        seen = members_by_user(view)
        assert seen[a]["reported"] is True and seen[a]["report_outcome"] is None   # partner: blind
        assert seen[b]["reported"] is False and seen[b]["report_outcome"] is None
    ev = world.client.get(f"{API}/events?party_id={party.id}", headers=world.headers["bob"]).json()
    recorded = [e for e in ev["events"] if e["event_type"] == "REPORT_RECORDED"]
    assert len(recorded) == 1 and recorded[0]["payload"] == {"reported": True}
    assert recorded[0]["actor_id"] == a
    assert "DID_NOT_HAPPEN" not in json.dumps(ev)
    row = [e for e in world.events(party.id) if e.event_type == "REPORT_RECORDED"][0]
    assert row.payload == {"reported": True}


def test_both_outcomes_are_revealed_once_the_party_ended(world, party):
    start_trip(world)
    a, b = world.users["alice"].id, world.users["bob"].id
    report(world, "alice", party.id, "COMPLETED")
    end = report(world, "bob", party.id, "DID_NOT_HAPPEN")
    assert end.json()["state"] == "DISPUTED"
    for who in ("alice", "bob"):
        seen = members_by_user(get_party(world, who, party.id).json())
        assert seen[a]["report_outcome"] == "COMPLETED" and seen[b]["report_outcome"] == "DID_NOT_HAPPEN"
        assert seen[a]["reported"] and seen[b]["reported"]
    ev = world.client.get(f"{API}/events?party_id={party.id}", headers=world.headers["alice"]).json()
    assert all(e["payload"] == {"reported": True}
               for e in ev["events"] if e["event_type"] == "REPORT_RECORDED")


def test_same_outcome_report_retry_while_agreed_is_idempotent(world, party):
    start_trip(world)
    first = report(world, "alice", party.id, "COMPLETED")
    version = first.json()["version"]
    again = report(world, "alice", party.id, "COMPLETED")
    assert again.status_code == 200 and again.json()["version"] == version
    assert len([e for e in world.events(party.id) if e.event_type == "REPORT_RECORDED"]) == 1
    assert world.get(cm.TravelParty, party.id).version == version
    # changing it is still allowed and is a new event
    changed = report(world, "alice", party.id, "DID_NOT_HAPPEN")
    assert changed.json()["version"] == version + 1


# ======================================================= replay privacy (cancel)
def test_cancel_replay_is_rebuilt_from_current_state_and_never_leaks(world, party):
    first = cancel(world, "alice", party.id, key="K")
    again = cancel(world, "alice", party.id, key="K")
    assert again.status_code == 200 and again.headers["Idempotent-Replay"] == "true"
    assert again.json() == get_party(world, "alice", party.id).json()
    assert again.json()["partner"]["phone_number"] is None and again.json()["partner"]["email"] is None
    assert "+91000" not in again.text and "@example.test" not in again.text
    # a stored body that DID contain contacts is never served back
    db = world.sf()
    rec = db.query(cm.IdempotencyRecord).filter_by(operation="cancel_party").one()
    rec.response_body = {**first.json(), "partner": {**first.json()["partner"],
                         "phone_number": "+910000000002", "email": "bob@example.test"}}
    db.commit()
    db.close()
    leak = cancel(world, "alice", party.id, key="K")
    assert "+910000000002" not in leak.text and "bob@example.test" not in leak.text
    # another user replaying alice's key is handled normally (carol: not a member)
    assert cancel(world, "carol", party.id, key="K").status_code == 404
    bob = cancel(world, "bob", party.id, key="K")  # bob has no record under this key
    assert bob.status_code == 200 and "Idempotent-Replay" not in bob.headers
    assert len(world.events(party.id, "PARTY_CANCELLED")) == 1


# ================================================================ departure range
@pytest.mark.parametrize("value", ["9999-12-31T23:00:00Z", "9999-12-31T23:00:00-05:00",
                                   "9999-12-31T23:59:59+14:00"])
def test_change_with_absurd_departure_is_422_not_500(world, party, value):
    resp = propose_change(world, "alice", party.id, 1, agreed_departure=value)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "departure_out_of_range"
    assert world.rows(cm.PartyChangeProposal) == []
    assert world.get(cm.TravelParty, party.id).version == 1


def test_change_departure_must_be_within_the_lead_time_limit(world, party):
    from app.core import campus_rules
    limit = world.clock.now + timedelta(days=campus_rules.MAX_LEAD_DAYS)
    too_far = propose_change(world, "alice", party.id, 1,
                             agreed_departure=iso(limit + timedelta(seconds=1)))
    assert too_far.status_code == 422 and code(too_far) == "departure_out_of_range"
    ok = propose_change(world, "alice", party.id, 1, agreed_departure=iso(limit))
    assert ok.status_code == 201


def test_change_with_absurd_landmark_id_is_422(world, party):
    resp = propose_change(world, "alice", party.id, 1, meeting_landmark_id=10 ** 25)
    assert resp.status_code == 422 and code(resp) == "invalid_landmark"


def test_time_out_never_raises_for_out_of_range_instants():
    from datetime import datetime
    from app.schemas.campus_schema import TimeOut
    out = TimeOut.of(datetime(9999, 12, 31, 23, 0), "Asia/Kolkata")
    assert out.utc.startswith("9999-12-31T23:00:00") and out.local


# ================================================= deadlock safety net (SQLite)
def fail_once(monkeypatch, name, times=1):
    from sqlalchemy.exc import OperationalError
    from app.services import campus_party_service as svc

    real, calls = getattr(svc, name), []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) <= times:
            raise OperationalError("SELECT ...", {}, Exception("deadlock detected"))
        return real(*a, **k)

    monkeypatch.setattr(svc, name, flaky)
    return calls


def test_cancel_retries_once_then_conflict_retry(world, monkeypatch):
    p1, p2 = world.party("alice", "bob"), world.party("carol", "dave")
    calls = fail_once(monkeypatch, "_lock_requests", times=1)
    assert cancel(world, "alice", p1.id).status_code == 200 and len(calls) == 2
    assert len(world.events(p1.id, "PARTY_CANCELLED")) == 1  # exactly one despite the retry
    fail_once(monkeypatch, "_lock_requests", times=2)
    resp = cancel(world, "carol", p2.id, key="z")
    assert resp.status_code == 409 and code(resp) == "conflict_retry"
    assert resp.json()["detail"]["current"]["party"]["state"] == "AGREED"
    assert world.get(cm.TravelParty, p2.id).state == PS.AGREED


def test_report_retries_once_then_conflict_retry(world, monkeypatch, party):
    start_trip(world)
    calls = fail_once(monkeypatch, "_lock_requests", times=1)
    assert report(world, "alice", party.id, "COMPLETED").status_code == 200 and len(calls) == 2
    assert len([e for e in world.events(party.id) if e.event_type == "REPORT_RECORDED"]) == 1
    fail_once(monkeypatch, "_lock_requests", times=2)
    resp = report(world, "bob", party.id, "COMPLETED")
    assert resp.status_code == 409 and code(resp) == "conflict_retry"
    assert resp.json()["detail"]["current"]["party"]["state"] == "AGREED"


def test_change_flow_and_note_retry_once_then_conflict_retry(world, monkeypatch, party):
    dep = iso(world.clock.now + timedelta(minutes=45))
    calls = fail_once(monkeypatch, "_lock_party", times=1)
    created = propose_change(world, "alice", party.id, 1, agreed_departure=dep)
    assert created.status_code == 201 and len(calls) == 2
    ch = created.json()

    fail_once(monkeypatch, "_lock_party", times=1)
    ok = decide(world, "bob", party.id, ch["id"], "approve", expected_party_version=2)
    assert ok.status_code == 200

    fail_once(monkeypatch, "_lock_party", times=1)
    note = world.client.patch(url(party.id), headers=world.headers["bob"],
                              json={"expected_version": 3, "cost_note": "50/50"})
    assert note.status_code == 200 and note.json()["cost_note"] == "50/50"

    for name, call in (
        ("propose", lambda: propose_change(world, "alice", party.id, 4, agreed_departure=dep)),
        ("note", lambda: world.client.patch(url(party.id), headers=world.headers["bob"],
                                            json={"expected_version": 4, "cost_note": "x"})),
    ):
        fail_once(monkeypatch, "_lock_party", times=2)
        resp = call()
        assert resp.status_code == 409 and code(resp) == "conflict_retry", name
        assert resp.json()["detail"]["current"]["party"]["version"] == 4

    # approve / reject / withdraw hit the same net
    good = propose_change(world, "alice", party.id, 4, agreed_departure=dep).json()
    for action, who, kw in (("approve", "bob", {"expected_party_version": 5}),
                            ("reject", "bob", {}), ("withdraw", "alice", {})):
        fail_once(monkeypatch, "_lock_party", times=2)
        resp = decide(world, who, party.id, good["id"], action, **kw)
        assert resp.status_code == 409 and code(resp) == "conflict_retry", action
        assert world.get(cm.PartyChangeProposal, good["id"]).state == cm.ChangeState.PENDING
