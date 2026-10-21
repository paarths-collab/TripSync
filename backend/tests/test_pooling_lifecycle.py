"""Lifecycle regression tests for pooling: matching, connection requests,
approvals, cancellation, notifications and recovery. Fictional data only.

Shared contract with chat authorization: an active ride is an APPROVED
connection whose two requests are both CONNECTED; ending a ride sets BOTH
requests to CANCELLED and leaves the connection APPROVED.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ws_manager import manager
from app.main import app
from app.models import pooling_model, user_model

RS = pooling_model.PoolingRequestStatus
CS = pooling_model.PoolingConnectionStatus

BODY = {
    "start_latitude": 19.0760,
    "start_longitude": 72.8777,
    "destination_latitude": 19.1200,
    "destination_longitude": 72.9000,
    "destination_name": "Fictional Hall",
}


def always(distance):
    async def fake(origin, destinations):
        return [distance for _ in destinations]
    return fake


# ----------------------------------------------------------------- helpers
def search(client, headers):
    r = client.post("/api/pool/requests", json=BODY, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def req_status(factory, request_id):
    db = factory()
    try:
        return db.get(pooling_model.PoolingRequest, request_id).status
    finally:
        db.close()


def conn_status(factory, connection_id):
    db = factory()
    try:
        return db.get(pooling_model.PoolingConnection, connection_id).status
    finally:
        db.close()


def send(client, headers, target_request_id):
    return client.post("/api/pool/connections/send", json={"target_request_id": target_request_id}, headers=headers)


def respond(client, headers, connection_id, action):
    return client.post(f"/api/pool/connections/{connection_id}/respond", json={"action": action}, headers=headers)


def types_for(ws_sent, user_id):
    return [m["type"] for uid, m in ws_sent if uid == user_id]


def msgs(ws_sent, user_id, type_):
    return [m for uid, m in ws_sent if uid == user_id and m["type"] == type_]


@pytest.fixture
def users(college, make_user):
    out = {}
    for name in ("alice", "bob", "carol"):
        user, headers = make_user(f"{name}@example.test", f"{name.title()} Example", college, phone="+10000000009")
        out[name] = (user, headers)
    return out


@pytest.fixture
def other_college(test_session_factory):
    db = test_session_factory()
    try:
        row = user_model.College(name="SPIT")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


@pytest.fixture
def pair(client, users, fake_distance_matrix, ws_sent):
    """alice and bob searched in that order: both MATCHED. Returns (alice_req, bob_req)."""
    fake_distance_matrix(always(1000.0))
    a = search(client, users["alice"][1])["request_id"]
    b = search(client, users["bob"][1])["request_id"]
    return a, b


@pytest.fixture
def ride(client, users, pair, ws_sent, test_session_factory):
    """alice -> bob request approved by bob: both CONNECTED. Returns dict."""
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]
    assert respond(client, users["bob"][1], cid, "approve").status_code == 200
    ws_sent.clear()
    return {"a": a, "b": b, "cid": cid}


# ---------------------------------------------------------------- matching
@pytest.mark.parametrize("distance,expected", [(5000.0, 1), (5001.0, 0)])
def test_radius_boundary_is_inclusive(distance, expected, client, users, fake_distance_matrix):
    fake_distance_matrix(always(distance))
    search(client, users["alice"][1])
    result = search(client, users["bob"][1])
    assert len(result["matches"]) == expected


def test_wrong_college_is_not_matched(client, users, make_user, other_college, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    _, outsider_h = make_user("dave@example.test", "Dave Example", other_college)
    search(client, outsider_h)
    assert search(client, users["alice"][1])["matches"] == []


def test_candidate_older_than_window_is_not_matched(client, users, fake_distance_matrix, test_session_factory):
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]
    db = test_session_factory()
    try:
        db.get(pooling_model.PoolingRequest, a).created_at = datetime.utcnow() - timedelta(minutes=16)
        db.commit()
    finally:
        db.close()
    assert search(client, users["bob"][1])["matches"] == []


def test_users_own_other_request_is_never_a_candidate(client, users, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    search(client, users["alice"][1])
    assert search(client, users["alice"][1])["matches"] == []


def test_match_notifies_waiting_user_after_commit(client, users, fake_distance_matrix, ws_sent, test_session_factory):
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]
    b = search(client, users["bob"][1])["request_id"]
    note = msgs(ws_sent, users["alice"][0].id, "match_found")
    assert len(note) == 1 and note[0]["match"]["request_id"] == b
    assert note[0]["match"]["phone_number"] is None and note[0]["match"]["email"] is None
    assert req_status(test_session_factory, a) == RS.MATCHED
    assert req_status(test_session_factory, b) == RS.MATCHED


def test_match_survives_notification_failure(client, users, fake_distance_matrix, monkeypatch, test_session_factory):
    async def boom(message, user_id):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(manager, "send_personal_message", boom)
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]
    result = search(client, users["bob"][1])
    assert len(result["matches"]) == 1
    assert req_status(test_session_factory, a) == RS.MATCHED


def test_third_rider_discovers_earlier_matched_requests(client, users, pair, make_user, college):
    a, b = pair
    _, carol_h = users["carol"]
    result = search(client, carol_h)
    assert sorted(m["request_id"] for m in result["matches"]) == sorted([a, b])


# ------------------------------------------------ new request supersedes old
def test_new_request_cancels_stale_matched_rejects_pending_and_notifies(
    client, users, pair, ws_sent, test_session_factory
):
    a, b = pair
    alice, alice_h = users["alice"]
    bob, bob_h = users["bob"]
    cid = send(client, bob_h, a).json()["connection_id"]  # bob -> alice pending
    ws_sent.clear()

    new_id = search(client, alice_h)["request_id"]  # alice starts over

    assert new_id not in (a, b)
    assert req_status(test_session_factory, a) == RS.CANCELLED
    assert conn_status(test_session_factory, cid) == CS.REJECTED
    # bob's own request is untouched (still matched), and he is told why the invite died
    assert req_status(test_session_factory, b) == RS.MATCHED
    rejected = msgs(ws_sent, bob.id, "connection_rejected")
    assert len(rejected) == 1
    assert rejected[0]["connection_id"] == cid
    assert rejected[0]["reason"] == "request_cancelled"
    assert rejected[0]["by_user"]["id"] == alice.id


def test_new_request_rejects_pending_where_user_was_receiver(
    client, users, pair, ws_sent, test_session_factory
):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]  # alice -> bob pending
    ws_sent.clear()

    search(client, users["bob"][1])  # bob starts over

    assert conn_status(test_session_factory, cid) == CS.REJECTED
    assert msgs(ws_sent, users["alice"][0].id, "connection_rejected")[0]["reason"] == "request_cancelled"
    # and bob can no longer approve it
    assert respond(client, users["bob"][1], cid, "approve").status_code == 409


def test_cannot_start_new_search_while_connected(client, users, ride, test_session_factory):
    r = client.post("/api/pool/requests", json=BODY, headers=users["alice"][1])
    assert r.status_code == 409
    assert "active ride" in r.json()["detail"]
    assert req_status(test_session_factory, ride["a"]) == RS.CONNECTED


# --------------------------------------------------- connection validation
def test_self_connection_is_400(client, users, pair):
    a, _ = pair
    assert send(client, users["alice"][1], a).status_code == 400


def test_nonexistent_target_is_404(client, users, pair):
    assert send(client, users["alice"][1], 99999).status_code == 404


def test_cancelled_target_is_409(client, users, pair, test_session_factory):
    a, b = pair
    assert client.delete(f"/api/pool/requests/{b}", headers=users["bob"][1]).status_code == 200
    assert send(client, users["alice"][1], b).status_code == 409


def test_target_in_other_college_is_rejected(client, users, make_user, other_college, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    _, outsider_h = make_user("dave@example.test", "Dave Example", other_college)
    outsider_req = search(client, outsider_h)["request_id"]
    search(client, users["alice"][1])
    r = send(client, users["alice"][1], outsider_req)
    assert r.status_code == 403


def test_duplicate_in_reverse_direction_is_400(client, users, pair):
    a, b = pair
    assert send(client, users["alice"][1], b).status_code == 200
    assert send(client, users["bob"][1], a).status_code == 400
    assert send(client, users["alice"][1], b).status_code == 400


def test_connected_user_cannot_send_new_requests(client, users, ride):
    # carol searches while alice/bob are connected; alice cannot invite her
    carol_req = search(client, users["carol"][1])["request_id"]
    assert send(client, users["alice"][1], carol_req).status_code == 409
    # and nobody can invite a connected request
    assert send(client, users["carol"][1], ride["a"]).status_code == 409


def test_sender_uses_newest_open_request(client, users, fake_distance_matrix, test_session_factory):
    fake_distance_matrix(always(100.0))
    old = search(client, users["alice"][1])["request_id"]
    bob_req = search(client, users["bob"][1])["request_id"]
    new = search(client, users["alice"][1])["request_id"]
    cid = send(client, users["alice"][1], bob_req).json()["connection_id"]
    db = test_session_factory()
    try:
        assert db.get(pooling_model.PoolingConnection, cid).sender_request_id == new
        assert old != new
    finally:
        db.close()


# ------------------------------------------------------------- approvals
def test_competing_approvals_only_first_wins(client, users, fake_distance_matrix, ws_sent, test_session_factory):
    fake_distance_matrix(always(100.0))
    alice, alice_h = users["alice"]
    bob, bob_h = users["bob"]
    carol, carol_h = users["carol"]
    b = search(client, bob_h)["request_id"]
    a = search(client, alice_h)["request_id"]
    c = search(client, carol_h)["request_id"]
    cid_a = send(client, alice_h, b).json()["connection_id"]
    cid_c = send(client, carol_h, b).json()["connection_id"]
    ws_sent.clear()

    assert respond(client, bob_h, cid_a, "approve").status_code == 200

    assert conn_status(test_session_factory, cid_a) == CS.APPROVED
    assert conn_status(test_session_factory, cid_c) == CS.REJECTED
    assert req_status(test_session_factory, a) == RS.CONNECTED
    assert req_status(test_session_factory, b) == RS.CONNECTED
    assert req_status(test_session_factory, c) == RS.MATCHED
    assert len(msgs(ws_sent, alice.id, "connection_approved")) == 1
    assert len(msgs(ws_sent, bob.id, "connection_approved")) == 1
    auto = msgs(ws_sent, carol.id, "connection_rejected")
    assert len(auto) == 1 and auto[0]["reason"] == "partner_unavailable" and auto[0]["connection_id"] == cid_c

    second = respond(client, bob_h, cid_c, "approve")
    assert second.status_code == 409
    assert conn_status(test_session_factory, cid_c) == CS.REJECTED
    assert req_status(test_session_factory, c) == RS.MATCHED
    assert req_status(test_session_factory, a) == RS.CONNECTED
    assert req_status(test_session_factory, b) == RS.CONNECTED

    # double approval of the same connection is also a conflict
    assert respond(client, bob_h, cid_a, "approve").status_code == 409


def test_approve_with_cancelled_request_is_409_and_no_resurrection(client, users, pair, ws_sent, test_session_factory):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]
    db = test_session_factory()
    try:  # simulate the race: alice's request got cancelled after the invite
        db.get(pooling_model.PoolingRequest, a).status = RS.CANCELLED
        db.commit()
    finally:
        db.close()
    ws_sent.clear()

    r = respond(client, users["bob"][1], cid, "approve")

    assert r.status_code == 409
    assert req_status(test_session_factory, a) == RS.CANCELLED
    assert req_status(test_session_factory, b) == RS.MATCHED
    assert conn_status(test_session_factory, cid) == CS.PENDING  # claim rolled back
    assert ws_sent == []


def test_approve_survives_notification_failure(client, users, pair, monkeypatch, test_session_factory):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]

    async def boom(message, user_id):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(manager, "send_personal_message", boom)

    r = respond(client, users["bob"][1], cid, "approve")

    assert r.status_code == 200
    assert conn_status(test_session_factory, cid) == CS.APPROVED
    assert req_status(test_session_factory, a) == RS.CONNECTED
    assert req_status(test_session_factory, b) == RS.CONNECTED


def test_reject_commits_then_notifies_and_survives_socket_failure(client, users, pair, monkeypatch, test_session_factory):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]

    async def boom(message, user_id):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(manager, "send_personal_message", boom)

    assert respond(client, users["bob"][1], cid, "reject").status_code == 200
    assert conn_status(test_session_factory, cid) == CS.REJECTED
    assert req_status(test_session_factory, a) == RS.MATCHED


def test_invalid_action_is_400_and_only_receiver_may_respond(client, users, pair, test_session_factory):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]
    assert respond(client, users["bob"][1], cid, "maybe").status_code == 400
    assert respond(client, users["alice"][1], cid, "approve").status_code == 403
    assert conn_status(test_session_factory, cid) == CS.PENDING


def test_approved_payloads_and_active_connection_shape(client, users, pair, ws_sent):
    a, b = pair
    cid = send(client, users["alice"][1], b).json()["connection_id"]
    ws_sent.clear()
    respond(client, users["bob"][1], cid, "approve")
    alice, bob = users["alice"][0], users["bob"][0]
    to_alice = msgs(ws_sent, alice.id, "connection_approved")[0]
    assert to_alice["user_request_id"] == a and to_alice["partner"]["id"] == bob.id
    assert to_alice["partner"]["request_id"] == b and to_alice["partner"]["phone_number"] == "+10000000009"

    active = client.get("/api/pool/connections/active", headers=users["bob"][1]).json()["connection"]
    assert active["id"] == cid and active["user_request_id"] == b and active["partner"]["id"] == alice.id


# ----------------------------------------------------------------- cancel
def test_cancel_connected_ride_cancels_both_requests_and_keeps_connection(
    client, users, ride, ws_sent, test_session_factory
):
    alice, alice_h = users["alice"]
    bob, bob_h = users["bob"]

    r = client.delete(f"/api/pool/requests/{ride['a']}", headers=alice_h)

    assert r.status_code == 200
    assert req_status(test_session_factory, ride["a"]) == RS.CANCELLED
    assert req_status(test_session_factory, ride["b"]) == RS.CANCELLED
    assert conn_status(test_session_factory, ride["cid"]) == CS.APPROVED
    notes = msgs(ws_sent, bob.id, "ride_cancelled")
    assert len(notes) == 1
    assert notes[0]["request_id"] == ride["b"] and notes[0]["connection_id"] == ride["cid"]
    assert notes[0]["by_user"]["id"] == alice.id and "cancelled the ride" in notes[0]["message"]

    # recovery: the partner learns the ride ended without the WebSocket event
    assert client.get("/api/pool/connections/active", headers=bob_h).json() == {"connection": None}
    current = client.get("/api/pool/requests/current", headers=bob_h).json()
    assert current["ride_ended"] is True
    assert current["connection"] is None
    assert current["request"]["id"] == ride["b"] and current["request"]["status"] == "cancelled"
    assert client.get("/api/pool/requests/current", headers=alice_h).json()["ride_ended"] is True


def test_cancel_is_idempotent(client, users, ride, ws_sent, test_session_factory):
    alice_h = users["alice"][1]
    assert client.delete(f"/api/pool/requests/{ride['a']}", headers=alice_h).status_code == 200
    ws_sent.clear()
    again = client.delete(f"/api/pool/requests/{ride['a']}", headers=alice_h)
    assert again.status_code == 200
    assert ws_sent == []
    # the partner ending an already-ended ride also succeeds
    assert client.delete(f"/api/pool/requests/{ride['b']}", headers=users["bob"][1]).status_code == 200
    assert conn_status(test_session_factory, ride["cid"]) == CS.APPROVED


def test_cancel_other_users_request_is_404(client, users, ride, test_session_factory):
    assert client.delete(f"/api/pool/requests/{ride['a']}", headers=users["carol"][1]).status_code == 404
    assert req_status(test_session_factory, ride["a"]) == RS.CONNECTED


def test_cancel_survives_notification_failure(client, users, ride, monkeypatch, test_session_factory):
    async def boom(message, user_id):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(manager, "send_personal_message", boom)
    assert client.delete(f"/api/pool/requests/{ride['a']}", headers=users["alice"][1]).status_code == 200
    assert req_status(test_session_factory, ride["b"]) == RS.CANCELLED


def test_cancel_failure_leaves_db_unchanged_then_retry_succeeds(
    client, users, ride, ws_sent, monkeypatch, test_session_factory
):
    real_commit = Session.commit
    state = {"failed": False}

    def flaky_commit(self):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("simulated database failure")
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", flaky_commit)
    lenient = TestClient(app, raise_server_exceptions=False)

    failed = lenient.delete(f"/api/pool/requests/{ride['a']}", headers=users["alice"][1])

    assert failed.status_code >= 500
    assert state["failed"] is True
    assert req_status(test_session_factory, ride["a"]) == RS.CONNECTED
    assert req_status(test_session_factory, ride["b"]) == RS.CONNECTED
    assert conn_status(test_session_factory, ride["cid"]) == CS.APPROVED
    assert msgs(ws_sent, users["bob"][0].id, "ride_cancelled") == []

    retry = client.delete(f"/api/pool/requests/{ride['a']}", headers=users["alice"][1])

    assert retry.status_code == 200
    assert req_status(test_session_factory, ride["a"]) == RS.CANCELLED
    assert req_status(test_session_factory, ride["b"]) == RS.CANCELLED
    assert len(msgs(ws_sent, users["bob"][0].id, "ride_cancelled")) == 1


def test_cancel_open_request_rejects_pending_and_notifies_counterparts(
    client, users, pair, ws_sent, test_session_factory
):
    a, b = pair
    cid_in = send(client, users["bob"][1], a).json()["connection_id"]  # bob -> alice
    ws_sent.clear()

    assert client.delete(f"/api/pool/requests/{a}", headers=users["alice"][1]).status_code == 200

    assert req_status(test_session_factory, a) == RS.CANCELLED
    assert conn_status(test_session_factory, cid_in) == CS.REJECTED
    note = msgs(ws_sent, users["bob"][0].id, "connection_rejected")
    assert len(note) == 1 and note[0]["reason"] == "request_cancelled"
    assert req_status(test_session_factory, b) == RS.MATCHED


# ----------------------------------------------------------------- current
def test_current_request_none_and_open_states(client, users, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    h = users["alice"][1]
    assert client.get("/api/pool/requests/current", headers=h).json() == {
        "request": None, "connection": None, "ride_ended": False
    }
    rid = search(client, h)["request_id"]
    body = client.get("/api/pool/requests/current", headers=h).json()
    assert body["request"]["id"] == rid and body["request"]["status"] == "active"
    assert body["request"]["destination_name"] == "Fictional Hall" and body["request"]["created_at"]
    assert body["connection"] is None and body["ride_ended"] is False


def test_current_request_reports_active_connection_and_not_ended(client, users, ride):
    body = client.get("/api/pool/requests/current", headers=users["bob"][1]).json()
    active = client.get("/api/pool/connections/active", headers=users["bob"][1]).json()["connection"]
    assert body["request"]["status"] == "connected"
    assert body["connection"] == active and body["ride_ended"] is False


def test_plain_cancel_without_ride_is_not_ride_ended(client, users, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    h = users["alice"][1]
    rid = search(client, h)["request_id"]
    assert client.delete(f"/api/pool/requests/{rid}", headers=h).status_code == 200
    body = client.get("/api/pool/requests/current", headers=h).json()
    assert body["request"]["status"] == "cancelled" and body["ride_ended"] is False


# ----------------------------------------- stale candidate list (provider race)
def _set_status(factory, request_id, status):
    db = factory()
    try:
        db.get(pooling_model.PoolingRequest, request_id).status = status
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("raced_status", [RS.CONNECTED, RS.CANCELLED])
def test_candidate_changed_during_provider_call_is_not_overwritten(
    raced_status, client, users, fake_distance_matrix, ws_sent, test_session_factory
):
    """The candidate list is read before the provider calls; a candidate that became
    CONNECTED/CANCELLED meanwhile must not be flipped back to MATCHED."""
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]

    async def racing(origin, destinations):
        _set_status(test_session_factory, a, raced_status)
        return [100.0 for _ in destinations]

    fake_distance_matrix(racing)
    ws_sent.clear()
    result = search(client, users["bob"][1])

    assert result["matches"] == []
    assert req_status(test_session_factory, a) == raced_status
    assert req_status(test_session_factory, result["request_id"]) == RS.ACTIVE
    assert msgs(ws_sent, users["alice"][0].id, "match_found") == []


def test_only_still_open_candidates_are_returned_and_notified(
    client, users, fake_distance_matrix, ws_sent, test_session_factory
):
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]
    c = search(client, users["carol"][1])["request_id"]  # matches alice -> both MATCHED

    async def racing(origin, destinations):
        _set_status(test_session_factory, a, RS.CONNECTED)  # alice got connected meanwhile
        return [100.0 for _ in destinations]

    fake_distance_matrix(racing)
    ws_sent.clear()
    result = search(client, users["bob"][1])

    assert [m["request_id"] for m in result["matches"]] == [c]
    assert req_status(test_session_factory, a) == RS.CONNECTED
    assert msgs(ws_sent, users["alice"][0].id, "match_found") == []
    assert len(msgs(ws_sent, users["carol"][0].id, "match_found")) == 1


def test_own_request_cancelled_during_provider_call_writes_nothing(
    client, users, fake_distance_matrix, ws_sent, test_session_factory
):
    fake_distance_matrix(always(100.0))
    a = search(client, users["alice"][1])["request_id"]
    holder = {}

    async def racing(origin, destinations):
        db = test_session_factory()
        try:  # bob's brand-new request (highest id) is cancelled while we search
            newest = db.query(pooling_model.PoolingRequest).order_by(pooling_model.PoolingRequest.id.desc()).first()
            holder["id"] = newest.id
            newest.status = RS.CANCELLED
            db.commit()
        finally:
            db.close()
        return [100.0 for _ in destinations]

    fake_distance_matrix(racing)
    ws_sent.clear()
    result = search(client, users["bob"][1])

    assert result["matches"] == []
    assert req_status(test_session_factory, holder["id"]) == RS.CANCELLED  # not resurrected
    assert req_status(test_session_factory, a) == RS.ACTIVE  # not flipped to MATCHED
    assert ws_sent == []


# --------------------------------------------------------------- NULL college
@pytest.fixture
def nocollege_users(make_user):
    nowhere = SimpleNamespace(id=None)
    return [make_user(f"nc{i}@example.test", f"NoCollege{i} Example", nowhere)[1] for i in range(2)]


def test_users_without_college_never_match_each_other(client, nocollege_users, fake_distance_matrix):
    async def must_not_be_called(origin, destinations):
        raise AssertionError("provider must not be called for college-less users")

    fake_distance_matrix(must_not_be_called)
    search(client, nocollege_users[0])
    assert search(client, nocollege_users[1])["matches"] == []


def test_users_without_college_cannot_connect(client, nocollege_users, users, fake_distance_matrix):
    fake_distance_matrix(always(100.0))
    r0 = search(client, nocollege_users[0])["request_id"]
    r1 = search(client, nocollege_users[1])["request_id"]
    assert send(client, nocollege_users[0], r1).status_code == 403
    # nor can a normal user reach them (and vice versa)
    alice_req = search(client, users["alice"][1])["request_id"]
    assert send(client, users["alice"][1], r0).status_code == 403
    assert send(client, nocollege_users[0], alice_req).status_code == 403
