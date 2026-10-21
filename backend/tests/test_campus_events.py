"""GET /api/campus/events and GET /api/campus/parties/active.

Parties are seeded directly in the database (never through the party
endpoints) with ``campus_events.record_party_event``.
"""

import asyncio
from datetime import timedelta

import pytest

from app.core import campus_rules, campus_time
from app.models.campus_model import (
    ChangeState,
    OutboxMessage,
    OutboxStatus,
    PartyChangeProposal,
    PartyEventType,
    PartyState,
    TravelParty,
)
from app.services import campus_outbox
from tests.campus_seed import add_event, end_party, seed_party

ALICE_PHONE = "+10000000001"
BOB_PHONE = "+10000000002"


@pytest.fixture
def world(college, make_user, landmarks, make_travel_request, test_session_factory, clock):
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone=ALICE_PHONE)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone=BOB_PHONE)
    carol, carol_h = make_user("carol@example.test", "Carol Example", college, phone="+10000000003")
    party_id = seed_party(test_session_factory, clock, landmarks, make_travel_request, alice, bob)
    return {
        "alice": alice, "alice_h": alice_h, "bob": bob, "bob_h": bob_h,
        "carol": carol, "carol_h": carol_h,
        "party_id": party_id, "factory": test_session_factory,
        "landmarks": landmarks, "make_request": make_travel_request, "clock": clock,
    }


def _outbox(factory, user_id=None):
    db = factory()
    try:
        q = db.query(OutboxMessage)
        if user_id is not None:
            q = q.filter(OutboxMessage.recipient_id == user_id)
        rows = q.order_by(OutboxMessage.id).all()
        return [(r.recipient_id, r.payload["version"], r.status) for r in rows]
    finally:
        db.close()


def _dispatch(factory):
    db = factory()
    try:
        return asyncio.run(campus_outbox.dispatch_pending(db))
    finally:
        db.close()


# --------------------------------------------------------------------------
# /events
# --------------------------------------------------------------------------
def test_events_are_ordered_filtered_and_include_the_current_view(client, world, clock):
    f = world["factory"]
    add_event(f, clock, world["party_id"], world["bob"].id, PartyEventType.NOTE_UPDATED,
              {"cost_note": "split"}, cost_note="split evenly")
    add_event(f, clock, world["party_id"], world["alice"].id, PartyEventType.NOTE_UPDATED, {})

    resp = client.get("/api/campus/events", headers=world["alice_h"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["party_id"] == world["party_id"]
    assert [e["version"] for e in body["events"]] == [1, 2, 3]
    assert [e["event_type"] for e in body["events"]] == [
        "PARTY_AGREED", "NOTE_UPDATED", "NOTE_UPDATED",
    ]
    assert body["events"][1]["actor_id"] == world["bob"].id
    assert body["events"][1]["payload"] == {"cost_note": "split"}
    assert body["events"][0]["occurred_at"].endswith("Z")
    assert body["latest_version"] == 3
    assert body["server_time"]
    # The snapshot lets a restarted client converge from this one call.
    assert body["party"]["id"] == world["party_id"]
    assert body["party"]["version"] == 3
    assert body["party"]["state"] == "AGREED"
    assert body["party"]["cost_note"] == "split evenly"

    since = client.get("/api/campus/events", params={"after_version": 1}, headers=world["alice_h"])
    assert [e["version"] for e in since.json()["events"]] == [2, 3]

    caught_up = client.get("/api/campus/events", params={"after_version": 3}, headers=world["alice_h"])
    assert caught_up.json()["events"] == []
    assert caught_up.json()["latest_version"] == 3
    assert caught_up.json()["party"]["version"] == 3

    beyond = client.get("/api/campus/events", params={"after_version": 50}, headers=world["alice_h"])
    assert beyond.status_code == 200
    assert beyond.json()["events"] == []


def test_events_view_is_viewer_specific(client, world):
    alice_view = client.get("/api/campus/events", headers=world["alice_h"]).json()["party"]
    bob_view = client.get("/api/campus/events", headers=world["bob_h"]).json()["party"]

    assert alice_view["partner"]["user_id"] == world["bob"].id
    assert alice_view["partner"]["phone_number"] == BOB_PHONE
    assert bob_view["partner"]["user_id"] == world["alice"].id
    assert bob_view["partner"]["phone_number"] == ALICE_PHONE
    assert [m["you"] for m in alice_view["members"]] == [True, False]
    assert [m["you"] for m in bob_view["members"]] == [False, True]


def test_events_without_any_party_returns_empty_nulls(client, world):
    resp = client.get("/api/campus/events", headers=world["carol_h"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["party_id"] is None
    assert body["events"] == []
    assert body["latest_version"] is None
    assert body["party"] is None


def test_events_non_member_party_is_404_and_leaks_nothing(client, world):
    for headers in (world["carol_h"],):
        resp = client.get(
            "/api/campus/events", params={"party_id": world["party_id"]}, headers=headers
        )
        assert resp.status_code == 404
        assert "alice@example.test" not in resp.text
        assert ALICE_PHONE not in resp.text
        assert "PARTY_AGREED" not in resp.text

    missing = client.get("/api/campus/events", params={"party_id": 987654}, headers=world["alice_h"])
    assert missing.status_code == 404


def test_events_negative_after_version_is_422(client, world):
    resp = client.get("/api/campus/events", params={"after_version": -1}, headers=world["alice_h"])
    assert resp.status_code == 422
    bad = client.get("/api/campus/events", params={"after_version": "x"}, headers=world["alice_h"])
    assert bad.status_code == 422


def test_events_require_authentication(client, world):
    assert client.get("/api/campus/events").status_code == 401
    assert client.get("/api/campus/parties/active").status_code == 401


def test_events_default_party_is_the_agreed_one_else_most_recent(
    client, world, clock, college, make_user
):
    f = world["factory"]
    # Before anything new: AGREED party is the default.
    assert client.get("/api/campus/events", headers=world["alice_h"]).json()["party_id"] == world["party_id"]

    # Party ends -> default falls back to the most recent party (now CANCELLED).
    end_party(f, clock, world["party_id"], world["alice"].id)
    body = client.get("/api/campus/events", headers=world["alice_h"]).json()
    assert body["party_id"] == world["party_id"]
    assert body["party"]["state"] == "CANCELLED"
    assert [e["event_type"] for e in body["events"]] == ["PARTY_AGREED", "PARTY_CANCELLED"]

    # A newer AGREED party for alice becomes the default; the old one is reachable by id.
    dave, _ = make_user("dave@example.test", "Dave Example", college, phone="+10000000004")
    newer = seed_party(f, clock, world["landmarks"], world["make_request"], world["alice"], dave)
    body = client.get("/api/campus/events", headers=world["alice_h"]).json()
    assert body["party_id"] == newer
    old = client.get("/api/campus/events", params={"party_id": world["party_id"]}, headers=world["alice_h"])
    assert old.status_code == 200
    assert old.json()["party"]["state"] == "CANCELLED"
    # Bob (member of the old party only) still defaults to it.
    assert client.get("/api/campus/events", headers=world["bob_h"]).json()["party_id"] == world["party_id"]


def test_events_ack_the_callers_outbox_rows_only(client, world, ws_delivery, clock):
    f = world["factory"]
    add_event(f, clock, world["party_id"], world["alice"].id)  # v2
    ws_delivery.fail_all()
    _dispatch(f)  # both users' rows stay PENDING (attempted once)
    alice, bob = world["alice"].id, world["bob"].id
    assert {s for _, _, s in _outbox(f)} == {OutboxStatus.PENDING}

    assert client.get("/api/campus/events", headers=world["alice_h"]).status_code == 200

    assert {s for _, _, s in _outbox(f, alice)} == {OutboxStatus.ACKED}
    assert {s for _, _, s in _outbox(f, bob)} == {OutboxStatus.PENDING}

    # An acked event is never pushed again, even once sockets work.
    ws_delivery.restore()
    clock.advance(seconds=campus_rules.OUTBOX_BACKOFF_MAX_SECONDS + 1)
    assert _dispatch(f) == 2  # only bob's two rows
    assert {uid for uid, _ in ws_delivery.sent} == {bob}


def test_events_after_version_still_acks_up_to_latest(client, world, clock):
    f = world["factory"]
    add_event(f, clock, world["party_id"], world["alice"].id)
    client.get("/api/campus/events", params={"after_version": 2}, headers=world["bob_h"])
    assert {s for _, _, s in _outbox(f, world["bob"].id)} == {OutboxStatus.ACKED}


def test_pending_change_appears_in_the_party_view(client, world, clock):
    f = world["factory"]
    db = f()
    try:
        db.add(
            PartyChangeProposal(
                party_id=world["party_id"], proposer_id=world["alice"].id,
                new_departure=campus_time.to_db(clock.now + timedelta(minutes=90)),
                new_meeting_landmark_id=world["landmarks"]["campus2"].id,
                note="Library is closer", expected_party_version=1,
                state=ChangeState.PENDING, created_at=campus_time.to_db(clock.now),
            )
        )
        db.commit()
    finally:
        db.close()

    for headers in (world["alice_h"], world["bob_h"]):
        party = client.get("/api/campus/events", headers=headers).json()["party"]
        change = party["pending_change"]
        assert change["state"] == "PENDING"
        assert change["proposer_id"] == world["alice"].id
        assert change["new_meeting_landmark"]["name"] == "Library"
        assert change["note"] == "Library is closer"
        assert change["new_departure"]["utc"].endswith("Z")
        # Party values have NOT changed yet.
        assert party["meeting_landmark"]["name"] == "Main Gate"

    active = client.get("/api/campus/parties/active", headers=world["bob_h"]).json()
    assert active["party"]["pending_change"]["id"] == change["id"]

    # A resolved proposal is no longer shown.
    db = f()
    try:
        db.query(PartyChangeProposal).update({"state": ChangeState.REJECTED})
        db.commit()
    finally:
        db.close()
    assert client.get("/api/campus/events", headers=world["bob_h"]).json()["party"]["pending_change"] is None


# --------------------------------------------------------------------------
# /parties/active
# --------------------------------------------------------------------------
def test_active_party_for_a_member(client, world):
    resp = client.get("/api/campus/parties/active", headers=world["alice_h"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["recently_ended"] is None
    assert body["latest_version"] == 1
    assert body["server_time"]
    party = body["party"]
    assert party["id"] == world["party_id"]
    assert party["state"] == "AGREED"
    assert party["version"] == 1
    assert party["partner"] == {
        "user_id": world["bob"].id, "full_name": "Bob Example",
        "phone_number": BOB_PHONE, "email": "bob@example.test",
    }
    assert party["agreed_departure"]["timezone"] == "Asia/Kolkata"
    assert party["agreed_departure"]["local"].endswith("+05:30")
    assert party["pending_change"] is None


def test_active_party_for_a_non_member_is_empty(client, world):
    body = client.get("/api/campus/parties/active", headers=world["carol_h"]).json()
    assert body["party"] is None
    assert body["recently_ended"] is None
    assert body["latest_version"] is None
    assert body["server_time"]
    assert "Alice" not in str(body) and "Bob" not in str(body)


def test_recently_ended_window_and_contact_hiding(client, world, clock):
    f = world["factory"]
    end_party(f, clock, world["party_id"], world["alice"].id)

    body = client.get("/api/campus/parties/active", headers=world["bob_h"]).json()
    assert body["party"] is None
    ended = body["recently_ended"]
    assert ended["id"] == world["party_id"]
    assert ended["state"] == "CANCELLED"
    assert ended["end_reason"] == "seed_cancel"
    assert ended["ended_at"] is not None
    assert body["latest_version"] == 2
    # Name stays, contact goes.
    assert ended["partner"]["full_name"] == "Alice Example"
    assert ended["partner"]["phone_number"] is None
    assert ended["partner"]["email"] is None
    assert ALICE_PHONE not in str(body) and "alice@example.test" not in str(body)

    # Still inside the window just before RECENT_ENDED_HOURS ...
    clock.advance(hours=campus_rules.RECENT_ENDED_HOURS, seconds=-1)
    inside = client.get("/api/campus/parties/active", headers=world["bob_h"]).json()
    assert inside["recently_ended"]["id"] == world["party_id"]
    # ... and gone once it has passed.
    clock.advance(seconds=2)
    outside = client.get("/api/campus/parties/active", headers=world["bob_h"]).json()
    assert outside["recently_ended"] is None
    assert outside["party"] is None
    assert outside["latest_version"] is None


@pytest.mark.parametrize(
    "state,event",
    [
        (PartyState.COMPLETED, PartyEventType.PARTY_COMPLETED),
        (PartyState.DISPUTED, PartyEventType.PARTY_DISPUTED),
    ],
)
def test_recently_ended_covers_completed_and_disputed(client, world, clock, state, event):
    end_party(world["factory"], clock, world["party_id"], world["alice"].id,
              state=state, event_type=event, reason=state.value.lower())
    ended = client.get("/api/campus/parties/active", headers=world["alice_h"]).json()["recently_ended"]
    assert ended["state"] == state.value
    assert ended["partner"]["phone_number"] is None


def test_active_party_and_recently_ended_can_coexist(client, world, clock, college, make_user):
    f = world["factory"]
    end_party(f, clock, world["party_id"], world["alice"].id)
    clock.advance(hours=1)
    dave, _ = make_user("dave@example.test", "Dave Example", college, phone="+10000000004")
    newer = seed_party(f, clock, world["landmarks"], world["make_request"], world["alice"], dave)

    body = client.get("/api/campus/parties/active", headers=world["alice_h"]).json()

    assert body["party"]["id"] == newer
    assert body["recently_ended"]["id"] == world["party_id"]
    assert body["latest_version"] == body["party"]["version"] == 1


def test_most_recent_ended_party_wins(client, world, clock, college, make_user):
    f = world["factory"]
    end_party(f, clock, world["party_id"], world["alice"].id)
    clock.advance(hours=2)
    dave, _ = make_user("dave@example.test", "Dave Example", college)
    second = seed_party(f, clock, world["landmarks"], world["make_request"], world["alice"], dave)
    end_party(f, clock, second, world["alice"].id)

    body = client.get("/api/campus/parties/active", headers=world["alice_h"]).json()
    assert body["recently_ended"]["id"] == second


# --------------------------------------------------------------------------
# reconciliation: two restarted clients converge
# --------------------------------------------------------------------------
def _fresh_client_sync(client, headers):
    """A client with no in-memory state: /parties/active, then /events from version 0."""
    active = client.get("/api/campus/parties/active", headers=headers).json()
    events = client.get("/api/campus/events", headers=headers).json()
    return active, events


def test_two_restarted_clients_converge_after_one_side_cancels(client, world, ws_delivery, clock):
    f = world["factory"]
    # The canceller's request is retried with the same key: still exactly one
    # PARTY_CANCELLED event (here: one direct state change + event).
    end_party(f, clock, world["party_id"], world["alice"].id)
    ws_delivery.fail_all()                      # the push to both phones is lost
    assert _dispatch(f) == 0
    assert {s for _, _, s in _outbox(f)} == {OutboxStatus.PENDING}

    a_active, a_events = _fresh_client_sync(client, world["alice_h"])
    b_active, b_events = _fresh_client_sync(client, world["bob_h"])

    for active, events in ((a_active, a_events), (b_active, b_events)):
        assert active["party"] is None
        assert active["recently_ended"]["state"] == "CANCELLED"
        assert active["latest_version"] == 2
        assert events["latest_version"] == 2
        assert events["party"]["state"] == "CANCELLED"
        assert events["party"]["version"] == 2
        assert [e["event_type"] for e in events["events"]] == ["PARTY_AGREED", "PARTY_CANCELLED"]
    # Same server state, whichever client asks.
    assert a_events["party"]["agreed_departure"] == b_events["party"]["agreed_departure"]
    assert a_events["latest_version"] == b_events["latest_version"]
    assert sum(e["event_type"] == "PARTY_CANCELLED" for e in a_events["events"]) == 1

    # A client that had seen v1 only catches up with just the cancel.
    catch_up = client.get("/api/campus/events", params={"after_version": 1}, headers=world["bob_h"]).json()
    assert [e["event_type"] for e in catch_up["events"]] == ["PARTY_CANCELLED"]

    # Fetching /events acked both users' rows: nothing left to push.
    assert {s for _, _, s in _outbox(f)} == {OutboxStatus.ACKED}
    ws_delivery.restore()
    clock.advance(seconds=campus_rules.OUTBOX_BACKOFF_MAX_SECONDS + 1)
    assert _dispatch(f) == 0


def test_lost_push_is_retried_later_and_marked_sent(client, world, ws_delivery, clock):
    f = world["factory"]
    end_party(f, clock, world["party_id"], world["alice"].id)
    ws_delivery.fail_all()
    assert _dispatch(f) == 0
    db = f()
    try:
        state_before = db.get(TravelParty, world["party_id"]).state
    finally:
        db.close()

    ws_delivery.restore()
    clock.advance(seconds=campus_rules.OUTBOX_BACKOFF_MAX_SECONDS + 1)
    assert _dispatch(f) == 4  # v1 + v2 for both members

    assert {s for _, _, s in _outbox(f)} == {OutboxStatus.SENT}
    cancelled = [m for _, m in ws_delivery.sent if m["event_type"] == "PARTY_CANCELLED"]
    assert len(cancelled) == 2
    db = f()
    try:
        assert db.get(TravelParty, world["party_id"]).state == state_before == PartyState.CANCELLED
    finally:
        db.close()
