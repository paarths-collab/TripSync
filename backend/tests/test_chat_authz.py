"""Authorization regression tests for chat HTTP routes and the chat/pool sockets.

Fictional data only. alice and bob are an approved ride pair; carol is a
bystander; dave only has a PENDING connection with alice.
"""

from datetime import datetime, timedelta

import pytest

from app.models.conversation_model import Conversation
from app.models.message_model import Message
from app.models.pooling_model import (
    PoolingConnection,
    PoolingConnectionStatus,
    PoolingRequest,
    PoolingRequestStatus,
)

ALICE_PHONE = "+10000000001"
FORBIDDEN = "Chat is only available with an approved ride partner"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _jwt(headers):
    return headers["Authorization"].split(" ", 1)[1]


def _seed_pair(factory, user_a, user_b, req_status, conn_status):
    """Insert two requests and one connection (a sends to b). Returns (conn_id, req_ids)."""
    db = factory()
    try:
        reqs = []
        for user in (user_a, user_b):
            req = PoolingRequest(
                user_id=user.id,
                status=req_status,
                start_latitude=19.0,
                start_longitude=72.8,
                destination_latitude=19.1,
                destination_longitude=72.9,
            )
            db.add(req)
            reqs.append(req)
        db.flush()
        conn = PoolingConnection(
            sender_request_id=reqs[0].id,
            receiver_request_id=reqs[1].id,
            status=conn_status,
        )
        db.add(conn)
        db.commit()
        return conn.id, [r.id for r in reqs]
    finally:
        db.close()


def _seed_conversation(factory, user_a, user_b, n_messages=0, sender=None, base=None):
    db = factory()
    try:
        conv = Conversation(user1_id=min(user_a.id, user_b.id), user2_id=max(user_a.id, user_b.id))
        db.add(conv)
        db.flush()
        base = base or datetime(2030, 1, 1)
        for i in range(n_messages):
            db.add(
                Message(
                    conversation_id=conv.id,
                    sender_id=(sender or user_a).id,
                    content=f"msg {i}",
                    created_at=base + timedelta(seconds=i),
                    is_read=False,
                )
            )
        db.commit()
        return conv.id
    finally:
        db.close()


def _set_request_status(factory, req_ids, status):
    db = factory()
    try:
        db.query(PoolingRequest).filter(PoolingRequest.id.in_(req_ids)).update(
            {"status": status}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _count(factory, model):
    db = factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


@pytest.fixture
def world(college, make_user, test_session_factory):
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone=ALICE_PHONE)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone="+10000000002")
    carol, carol_h = make_user("carol@example.test", "Carol Example", college, phone="+10000000003")
    dave, dave_h = make_user("dave@example.test", "Dave Example", college, phone="+10000000004")

    conn_id, req_ids = _seed_pair(
        test_session_factory, alice, bob, PoolingRequestStatus.CONNECTED, PoolingConnectionStatus.APPROVED
    )
    _seed_pair(
        test_session_factory, alice, dave, PoolingRequestStatus.MATCHED, PoolingConnectionStatus.PENDING
    )
    return {
        "alice": alice, "alice_h": alice_h,
        "bob": bob, "bob_h": bob_h,
        "carol": carol, "carol_h": carol_h,
        "dave": dave, "dave_h": dave_h,
        "conn_id": conn_id, "req_ids": req_ids,
    }


# --------------------------------------------------------------------------
# a. find-or-create
# --------------------------------------------------------------------------
def test_stranger_cannot_find_or_create_and_nothing_leaks(client, world, test_session_factory):
    resp = client.get(
        "/api/chat/conversations/find-or-create",
        params={"partner_id": world["alice"].id},
        headers=world["carol_h"],
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    assert "alice@example.test" not in resp.text
    assert ALICE_PHONE not in resp.text
    assert _count(test_session_factory, Conversation) == 0


def test_find_or_create_self_is_400_and_unknown_is_404(client, world):
    me = client.get(
        "/api/chat/conversations/find-or-create",
        params={"partner_id": world["alice"].id},
        headers=world["alice_h"],
    )
    ghost = client.get(
        "/api/chat/conversations/find-or-create",
        params={"partner_id": 99999},
        headers=world["alice_h"],
    )
    assert me.status_code == 400
    assert ghost.status_code == 404


# --------------------------------------------------------------------------
# b / c / d / e. stranger access
# --------------------------------------------------------------------------
def test_stranger_conversation_list_is_empty(client, world, test_session_factory):
    _seed_conversation(test_session_factory, world["alice"], world["bob"], n_messages=2)

    resp = client.get("/api/chat/conversations", headers=world["carol_h"])

    assert resp.status_code == 200
    assert resp.json() == {"conversations": []}
    for secret in ("alice@example.test", "bob@example.test", ALICE_PHONE, "+10000000002"):
        assert secret not in resp.text


def test_stranger_cannot_mark_read_and_missing_is_404(client, world, test_session_factory):
    conv_id = _seed_conversation(test_session_factory, world["alice"], world["bob"], n_messages=3)

    resp = client.post(f"/api/chat/messages/{conv_id}/read", headers=world["carol_h"])
    missing = client.post("/api/chat/messages/99999/read", headers=world["carol_h"])

    assert resp.status_code == 403
    assert missing.status_code == 404
    db = test_session_factory()
    try:
        flags = [m.is_read for m in db.query(Message).filter(Message.conversation_id == conv_id)]
    finally:
        db.close()
    assert flags == [False, False, False]


def test_member_can_mark_read(client, world, test_session_factory):
    conv_id = _seed_conversation(test_session_factory, world["alice"], world["bob"], n_messages=3)

    resp = client.post(f"/api/chat/messages/{conv_id}/read", headers=world["bob_h"])

    assert resp.status_code == 200
    assert resp.json() == {"marked_read": 3}


def test_stranger_cannot_read_history(client, world, test_session_factory):
    conv_id = _seed_conversation(test_session_factory, world["alice"], world["bob"], n_messages=2)

    resp = client.get(f"/api/chat/messages/{conv_id}", headers=world["carol_h"])

    assert resp.status_code == 403
    assert "msg 0" not in resp.text


def test_stranger_message_forbidden_and_self_message_400(client, world, test_session_factory):
    to_alice = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["alice"].id, "content": "hi"},
        headers=world["carol_h"],
    )
    to_self = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["carol"].id, "content": "hi me"},
        headers=world["carol_h"],
    )
    to_ghost = client.post(
        "/api/chat/messages",
        json={"receiver_id": 99999, "content": "anyone"},
        headers=world["carol_h"],
    )

    assert to_alice.status_code == 403
    assert to_self.status_code == 400
    assert to_ghost.status_code == 404
    assert _count(test_session_factory, Conversation) == 0
    assert _count(test_session_factory, Message) == 0


# --------------------------------------------------------------------------
# g. unapproved pair
# --------------------------------------------------------------------------
def test_unapproved_pair_cannot_chat_and_list_hides_details(client, world, test_session_factory):
    resp = client.get(
        "/api/chat/conversations/find-or-create",
        params={"partner_id": world["dave"].id},
        headers=world["alice_h"],
    )
    assert resp.status_code == 403
    assert "dave@example.test" not in resp.text

    _seed_conversation(test_session_factory, world["alice"], world["dave"], n_messages=1, sender=world["dave"])
    listing = client.get("/api/chat/conversations", headers=world["alice_h"])

    assert listing.status_code == 200
    partner = listing.json()["conversations"][0]["partner"]
    assert partner["id"] == world["dave"].id
    assert partner["full_name"] == "Dave Example"
    assert partner["phone_number"] is None
    assert partner["email"] is None
    assert partner["bio"] is None
    assert partner["year_of_study"] is None
    assert "dave@example.test" not in listing.text
    assert "+10000000004" not in listing.text


# --------------------------------------------------------------------------
# h. approved pair, then cancelled ride
# --------------------------------------------------------------------------
def test_approved_pair_flow_then_ride_cancelled(client, world, test_session_factory):
    alice_h, bob = world["alice_h"], world["bob"]

    found = client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": bob.id}, headers=alice_h
    )
    assert found.status_code == 200
    body = found.json()
    assert body["partner"] == {"id": bob.id, "full_name": "Bob Example", "email": "bob@example.test"}
    conv_id = body["conversation_id"]

    sent = client.post(
        "/api/chat/messages", json={"receiver_id": bob.id, "content": "see you at 9"}, headers=alice_h
    )
    assert sent.status_code == 200
    assert sent.json()["conversation_id"] == conv_id

    listing = client.get("/api/chat/conversations", headers=world["bob_h"]).json()["conversations"]
    assert len(listing) == 1
    assert listing[0]["partner"]["phone_number"] == ALICE_PHONE
    assert listing[0]["partner"]["email"] == "alice@example.test"

    # Ride cancelled: both requests CANCELLED, connection stays APPROVED.
    _set_request_status(test_session_factory, world["req_ids"], PoolingRequestStatus.CANCELLED)

    after = client.post(
        "/api/chat/messages", json={"receiver_id": bob.id, "content": "still there?"}, headers=alice_h
    )
    assert after.status_code == 403

    hidden = client.get("/api/chat/conversations", headers=world["bob_h"])
    partner = hidden.json()["conversations"][0]["partner"]
    assert partner["id"] == world["alice"].id
    assert partner["phone_number"] is None
    assert partner["email"] is None
    assert ALICE_PHONE not in hidden.text
    assert "alice@example.test" not in hidden.text

    history = client.get(f"/api/chat/messages/{conv_id}", headers=world["bob_h"])
    assert history.status_code == 200
    assert [m["content"] for m in history.json()["messages"]] == ["see you at 9"]

    refind = client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": bob.id}, headers=alice_h
    )
    assert refind.status_code == 403


def test_reverse_direction_connection_is_also_active(client, college, make_user, test_session_factory):
    x, x_h = make_user("x@example.test", "X Example", college)
    y, _ = make_user("y@example.test", "Y Example", college)
    # y is the sender, x the receiver.
    _seed_pair(test_session_factory, y, x, PoolingRequestStatus.CONNECTED, PoolingConnectionStatus.APPROVED)

    resp = client.get("/api/chat/conversations/find-or-create", params={"partner_id": y.id}, headers=x_h)

    assert resp.status_code == 200


# --------------------------------------------------------------------------
# k. latest-N ordering
# --------------------------------------------------------------------------
def test_get_messages_returns_latest_100_in_ascending_order(client, world, test_session_factory):
    conv_id = _seed_conversation(test_session_factory, world["alice"], world["bob"], n_messages=105)

    resp = client.get(f"/api/chat/messages/{conv_id}", headers=world["bob_h"])

    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()["messages"]]
    assert contents == [f"msg {i}" for i in range(5, 105)]


# --------------------------------------------------------------------------
# f. pool socket relay
# --------------------------------------------------------------------------
def _pool_ws(client, headers):
    return client.websocket_connect("/api/ws/pool", subprotocols=["token", _jwt(headers)])


def _chat_ws(client, headers):
    return client.websocket_connect("/api/ws/chat", subprotocols=["token", _jwt(headers)])


def test_pool_socket_refuses_stranger_relay(client, world, ws_sent):
    with _pool_ws(client, world["carol_h"]) as ws:
        ws.send_json(
            {"type": "chat_message", "receiver_id": world["alice"].id, "connection_id": world["conn_id"], "content": "psst"}
        )
        frame = ws.receive_json()

    assert frame["type"] == "error"
    assert frame["code"] == "not_authorized"
    assert ws_sent == []


def test_pool_socket_forwards_between_approved_pair(client, world, ws_sent):
    with _pool_ws(client, world["alice_h"]) as ws:
        ws.send_json(
            {
                "type": "chat_message",
                "receiver_id": world["bob"].id,
                "connection_id": world["conn_id"],
                "content": "hello bob",
                "created_at": "2030-01-01T00:00:00Z",
            }
        )
        ws.send_json([])  # barrier: its error reply proves the first frame was processed
        assert ws.receive_json()["type"] == "error"

    assert len(ws_sent) == 1
    user_id, payload = ws_sent[0]
    assert user_id == world["bob"].id
    assert payload == {
        "type": "chat_message",
        "sender_id": world["alice"].id,
        "sender_name": "Alice Example",
        "content": "hello bob",
        "connection_id": world["conn_id"],
        "created_at": "2030-01-01T00:00:00Z",
    }


def test_pool_socket_uses_server_connection_id_and_rejects_wrong_one(client, world, ws_sent):
    with _pool_ws(client, world["alice_h"]) as ws:
        ws.send_json(
            {"type": "chat_message", "receiver_id": world["bob"].id, "connection_id": world["conn_id"] + 100, "content": "x"}
        )
        refused = ws.receive_json()
        ws.send_json({"type": "chat_message", "receiver_id": world["bob"].id, "content": "no conn id"})
        ws.send_json([])
        ws.receive_json()

    assert refused["code"] == "not_authorized"
    assert [(uid, p["connection_id"]) for uid, p in ws_sent] == [(world["bob"].id, world["conn_id"])]


def test_pool_socket_malformed_frames_keep_socket_usable(client, world, ws_sent):
    with _pool_ws(client, world["alice_h"]) as ws:
        ws.send_text("[]")
        assert ws.receive_json()["type"] == "error"
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "chat_message", "receiver_id": "abc", "content": "x"})
        assert ws.receive_json()["code"] == "not_authorized"
        ws.send_json({"type": "chat_message", "receiver_id": world["alice"].id, "content": "me"})
        assert ws.receive_json()["code"] == "not_authorized"
        ws.send_json({"type": "chat_message", "receiver_id": world["bob"].id, "content": "ok"})
        ws.send_json([])
        assert ws.receive_json()["type"] == "error"

    assert [uid for uid, _ in ws_sent] == [world["bob"].id]


def test_pool_socket_honours_ride_cancelled_mid_socket(client, world, ws_sent, test_session_factory):
    msg = {"type": "chat_message", "receiver_id": world["bob"].id, "content": "hi"}
    with _pool_ws(client, world["alice_h"]) as ws:
        ws.send_json(msg)
        ws.send_json([])
        ws.receive_json()
        assert len(ws_sent) == 1

        _set_request_status(test_session_factory, world["req_ids"], PoolingRequestStatus.CANCELLED)

        ws.send_json(msg)
        frame = ws.receive_json()

    assert frame["code"] == "not_authorized"
    assert len(ws_sent) == 1


def test_pool_socket_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/pool", subprotocols=["token", "garbage"]):
            pass


# --------------------------------------------------------------------------
# i. chat socket
# --------------------------------------------------------------------------
def test_chat_socket_forwards_between_approved_pair(client, world, ws_sent):
    with _chat_ws(client, world["alice_h"]) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        ws.send_json(
            {
                "type": "chat_message",
                "receiver_id": world["bob"].id,
                "connection_id": world["conn_id"],
                "message_id": 7,
                "content": "hello via chat socket",
                "created_at": "2030-01-01T00:00:00Z",
            }
        )
        ws.send_json([])
        assert ws.receive_json()["type"] == "error"

    assert ws_sent == [
        (
            world["bob"].id,
            {
                "type": "chat_message",
                "message_id": 7,
                "connection_id": world["conn_id"],
                "sender_id": world["alice"].id,
                "content": "hello via chat socket",
                "created_at": "2030-01-01T00:00:00Z",
            },
        )
    ]


def test_chat_socket_refuses_stranger_and_unapproved(client, world, ws_sent):
    with _chat_ws(client, world["carol_h"]) as ws:
        ws.send_json({"type": "chat_message", "receiver_id": world["alice"].id, "content": "psst"})
        stranger = ws.receive_json()

    with _chat_ws(client, world["alice_h"]) as ws:
        ws.send_json({"type": "chat_message", "receiver_id": world["dave"].id, "content": "pending only"})
        pending = ws.receive_json()

    assert stranger["type"] == "error" and stranger["code"] == "not_authorized"
    assert pending["type"] == "error" and pending["code"] == "not_authorized"
    assert ws_sent == []


def test_chat_socket_refused_after_cancel_and_rejects_bad_token(client, world, ws_sent, test_session_factory):
    _set_request_status(test_session_factory, world["req_ids"], PoolingRequestStatus.CANCELLED)

    with _chat_ws(client, world["alice_h"]) as ws:
        ws.send_json({"type": "chat_message", "receiver_id": world["bob"].id, "content": "late"})
        frame = ws.receive_json()

    assert frame["code"] == "not_authorized"
    assert ws_sent == []

    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/chat", subprotocols=["token", "garbage"]):
            pass
