"""End-to-end two-user ride flow: match, connect, approve, chat, cancel.

Fictional data only. alice and bob ride together; carol is a bystander in the
same college. Every step checks what both riders see, not just the caller.
"""

from app.models.conversation_model import Conversation
from app.models.message_model import Message
from app.models.pooling_model import (
    PoolingConnection,
    PoolingConnectionStatus,
    PoolingRequest,
    PoolingRequestStatus,
)

ALICE_PHONE = "+10000000001"
BOB_PHONE = "+10000000002"
CAROL_PHONE = "+10000000003"
FAKE_DISTANCE_METRES = 1000.0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
async def _fake_distances(origin, destinations):
    return [FAKE_DISTANCE_METRES for _ in destinations]


def _jwt(headers):
    return headers["Authorization"].split(" ", 1)[1]


def _pool_ws(client, headers):
    return client.websocket_connect("/api/ws/pool", subprotocols=["token", _jwt(headers)])


def _create_request(client, headers, destination_name="Gate 2"):
    return client.post(
        "/api/pool/requests",
        json={
            "start_latitude": 19.0,
            "start_longitude": 72.8,
            "destination_latitude": 19.1,
            "destination_longitude": 72.9,
            "destination_name": destination_name,
        },
        headers=headers,
    )


def _events(ws_sent, user_id, msg_type):
    return [m for uid, m in ws_sent if uid == user_id and m.get("type") == msg_type]


def _count(factory, model):
    db = factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


def _request_statuses(factory, request_ids):
    db = factory()
    try:
        rows = db.query(PoolingRequest).filter(PoolingRequest.id.in_(request_ids)).all()
        return {r.id: r.status for r in rows}
    finally:
        db.close()


def _connection_status(factory, connection_id):
    db = factory()
    try:
        return db.query(PoolingConnection).filter(PoolingConnection.id == connection_id).one().status
    finally:
        db.close()


def _message_rows(factory, conversation_id):
    db = factory()
    try:
        rows = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id)
            .all()
        )
        return [(m.content, m.sender_id, m.is_read) for m in rows]
    finally:
        db.close()


def _assert_ride_ended(client, headers):
    assert client.get("/api/pool/connections/active", headers=headers).json() == {"connection": None}
    current = client.get("/api/pool/requests/current", headers=headers).json()
    assert str(current["request"]["status"]).lower() == "cancelled"
    assert current["connection"] is None
    assert current["ride_ended"] is True


def _approve_pair(client, alice_h, bob_h, alice_request_id):
    """Bob asks to connect to Alice's request and Alice approves. Returns connection id."""
    sent = client.post(
        "/api/pool/connections/send", json={"target_request_id": alice_request_id}, headers=bob_h
    )
    assert sent.status_code == 200
    connection_id = sent.json()["connection_id"]
    approved = client.post(
        f"/api/pool/connections/{connection_id}/respond", json={"action": "approve"}, headers=alice_h
    )
    assert approved.status_code == 200
    return connection_id


# --------------------------------------------------------------------------
# Scenario
# --------------------------------------------------------------------------
def test_match_approve_chat_cancel_is_consistent_for_both_users(
    client, college, make_user, test_session_factory, ws_sent, fake_distance_matrix
):
    fake_distance_matrix(_fake_distances)
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone=ALICE_PHONE)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone=BOB_PHONE)
    carol, carol_h = make_user("carol@example.test", "Carol Example", college, phone=CAROL_PHONE)

    # 1. Alice searches first and finds nothing; Bob's nearby search matches her.
    alice_search = _create_request(client, alice_h)
    assert alice_search.status_code == 200
    assert alice_search.json()["matches"] == []
    alice_request_id = alice_search.json()["request_id"]

    bob_search = _create_request(client, bob_h)
    assert bob_search.status_code == 200
    bob_body = bob_search.json()
    bob_request_id = bob_body["request_id"]
    assert len(bob_body["matches"]) == 1
    match = bob_body["matches"][0]
    assert match["id"] == alice.id
    assert match["request_id"] == alice_request_id
    assert match["full_name"] == "Alice Example"
    assert match["phone_number"] is None
    assert match["email"] is None
    assert match["bio"] is None
    assert match["year_of_study"] is None
    assert match["connection_status"] == "none"

    match_found = _events(ws_sent, alice.id, "match_found")
    assert len(match_found) == 1
    assert match_found[0]["match"]["id"] == bob.id
    assert match_found[0]["match"]["request_id"] == bob_request_id
    assert match_found[0]["match"]["phone_number"] is None
    assert match_found[0]["match"]["email"] is None

    # 2. Bob asks to connect. Nothing is open to chat until Alice approves.
    sent = client.post(
        "/api/pool/connections/send", json={"target_request_id": alice_request_id}, headers=bob_h
    )
    assert sent.status_code == 200
    connection_id = sent.json()["connection_id"]
    assert sent.json()["status"] == "pending"

    received = _events(ws_sent, alice.id, "connection_request_received")
    assert len(received) == 1
    assert received[0]["connection_id"] == connection_id
    assert received[0]["from_user"]["id"] == bob.id

    assert client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": alice.id}, headers=bob_h
    ).status_code == 403
    assert client.post(
        "/api/chat/messages", json={"receiver_id": alice.id, "content": "too early"}, headers=bob_h
    ).status_code == 403
    assert client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": alice.id}, headers=carol_h
    ).status_code == 403
    assert _count(test_session_factory, Conversation) == 0
    assert _count(test_session_factory, Message) == 0

    # 3. Alice approves: both sides see the approval and the partner's contact details.
    approve = client.post(
        f"/api/pool/connections/{connection_id}/respond", json={"action": "approve"}, headers=alice_h
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    alice_approved = _events(ws_sent, alice.id, "connection_approved")
    bob_approved = _events(ws_sent, bob.id, "connection_approved")
    assert len(alice_approved) == 1
    assert len(bob_approved) == 1
    assert alice_approved[0]["partner"]["id"] == bob.id
    assert alice_approved[0]["partner"]["phone_number"] == BOB_PHONE
    assert alice_approved[0]["partner"]["email"] == "bob@example.test"
    assert bob_approved[0]["partner"]["id"] == alice.id
    assert bob_approved[0]["partner"]["phone_number"] == ALICE_PHONE
    assert bob_approved[0]["partner"]["email"] == "alice@example.test"

    alice_active = client.get("/api/pool/connections/active", headers=alice_h).json()["connection"]
    assert alice_active["partner"]["id"] == bob.id
    assert alice_active["partner"]["phone_number"] == BOB_PHONE
    assert alice_active["partner"]["email"] == "bob@example.test"

    bob_active = client.get("/api/pool/connections/active", headers=bob_h).json()["connection"]
    assert bob_active["partner"]["id"] == alice.id
    assert bob_active["partner"]["phone_number"] == ALICE_PHONE
    assert bob_active["partner"]["email"] == "alice@example.test"

    for headers in (alice_h, bob_h):
        current = client.get("/api/pool/requests/current", headers=headers).json()
        assert current["connection"] is not None
        assert current["ride_ended"] is False
        assert str(current["request"]["status"]).lower() == "connected"

    # 4. Chat between the approved pair; carol is shut out at every entry point.
    found = client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": bob.id}, headers=alice_h
    )
    assert found.status_code == 200
    conv_id = found.json()["conversation_id"]

    sent_msg = client.post(
        "/api/chat/messages", json={"receiver_id": bob.id, "content": "Meet at gate 2"}, headers=alice_h
    )
    assert sent_msg.status_code == 200
    assert sent_msg.json()["conversation_id"] == conv_id

    bob_history = client.get(f"/api/chat/messages/{conv_id}", headers=bob_h)
    assert bob_history.status_code == 200
    assert [m["content"] for m in bob_history.json()["messages"]] == ["Meet at gate 2"]

    bob_convs = client.get("/api/chat/conversations", headers=bob_h).json()["conversations"]
    assert len(bob_convs) == 1
    assert bob_convs[0]["partner"]["phone_number"] == ALICE_PHONE
    assert bob_convs[0]["partner"]["email"] == "alice@example.test"

    assert client.post(f"/api/chat/messages/{conv_id}/read", headers=bob_h).status_code == 200

    assert client.get(f"/api/chat/messages/{conv_id}", headers=carol_h).status_code == 403
    assert client.post(f"/api/chat/messages/{conv_id}/read", headers=carol_h).status_code == 403
    assert client.post(
        "/api/chat/messages", json={"receiver_id": alice.id, "content": "carol here"}, headers=carol_h
    ).status_code == 403
    assert client.get("/api/chat/conversations", headers=carol_h).json() == {"conversations": []}
    assert _message_rows(test_session_factory, conv_id) == [("Meet at gate 2", alice.id, True)]

    before_carol_socket = len(ws_sent)
    with _pool_ws(client, carol_h) as ws:
        ws.send_json(
            {
                "type": "chat_message",
                "receiver_id": alice.id,
                "connection_id": connection_id,
                "content": "psst",
            }
        )
        frame = ws.receive_json()
    assert frame["type"] == "error"
    assert frame["code"] == "not_authorized"
    assert ws_sent[before_carol_socket:] == []

    # 5. Alice ends the ride: Bob is told, both sides see it ended, DB agrees.
    cancel = client.delete(f"/api/pool/requests/{alice_request_id}", headers=alice_h)
    assert cancel.status_code == 200

    ride_cancelled = _events(ws_sent, bob.id, "ride_cancelled")
    assert len(ride_cancelled) == 1
    assert ride_cancelled[0]["request_id"] == bob_request_id
    assert ride_cancelled[0]["connection_id"] == connection_id
    assert ride_cancelled[0]["by_user"]["id"] == alice.id
    assert _events(ws_sent, alice.id, "ride_cancelled") == []

    _assert_ride_ended(client, alice_h)
    _assert_ride_ended(client, bob_h)

    assert _request_statuses(test_session_factory, [alice_request_id, bob_request_id]) == {
        alice_request_id: PoolingRequestStatus.CANCELLED,
        bob_request_id: PoolingRequestStatus.CANCELLED,
    }
    assert _connection_status(test_session_factory, connection_id) == PoolingConnectionStatus.APPROVED

    # 6. After the ride: no new messages, history stays readable, contacts hidden.
    for headers, partner_id in ((alice_h, bob.id), (bob_h, alice.id)):
        blocked = client.post(
            "/api/chat/messages", json={"receiver_id": partner_id, "content": "after the ride"}, headers=headers
        )
        assert blocked.status_code == 403

    assert _count(test_session_factory, Message) == 1

    for headers in (alice_h, bob_h):
        history = client.get(f"/api/chat/messages/{conv_id}", headers=headers)
        assert history.status_code == 200
        assert [m["content"] for m in history.json()["messages"]] == ["Meet at gate 2"]

        listing = client.get("/api/chat/conversations", headers=headers)
        convs = listing.json()["conversations"]
        assert len(convs) == 1
        assert convs[0]["partner"]["phone_number"] is None
        assert convs[0]["partner"]["email"] is None
        for secret in (ALICE_PHONE, BOB_PHONE, "alice@example.test", "bob@example.test"):
            assert secret not in listing.text

    # 7. Retries are harmless: no new notifications, and Bob can search again.
    before_retries = len(ws_sent)

    alice_retry = client.delete(f"/api/pool/requests/{alice_request_id}", headers=alice_h)
    assert alice_retry.status_code == 200

    bob_cancel = client.delete(f"/api/pool/requests/{bob_request_id}", headers=bob_h)
    assert bob_cancel.status_code == 200

    assert ws_sent[before_retries:] == []

    bob_new_search = _create_request(client, bob_h, destination_name="Gate 2 again")
    assert bob_new_search.status_code == 200
    assert bob_new_search.json()["request_id"] != bob_request_id


# --------------------------------------------------------------------------
# Smaller tests
# --------------------------------------------------------------------------
def test_rejected_connection_keeps_chat_closed_and_contacts_hidden(
    client, college, make_user, test_session_factory, ws_sent, fake_distance_matrix
):
    fake_distance_matrix(_fake_distances)
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone=ALICE_PHONE)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone=BOB_PHONE)

    alice_request_id = _create_request(client, alice_h).json()["request_id"]
    bob_request_id = _create_request(client, bob_h).json()["request_id"]

    sent = client.post(
        "/api/pool/connections/send", json={"target_request_id": alice_request_id}, headers=bob_h
    )
    assert sent.status_code == 200
    connection_id = sent.json()["connection_id"]

    reject = client.post(
        f"/api/pool/connections/{connection_id}/respond", json={"action": "reject"}, headers=alice_h
    )
    assert reject.status_code == 200

    rejected = _events(ws_sent, bob.id, "connection_rejected")
    assert len(rejected) == 1
    assert rejected[0]["connection_id"] == connection_id
    assert rejected[0]["by_user"]["id"] == alice.id

    assert client.get(
        "/api/chat/conversations/find-or-create", params={"partner_id": alice.id}, headers=bob_h
    ).status_code == 403
    assert client.get("/api/pool/connections/active", headers=bob_h).json() == {"connection": None}
    assert client.get("/api/pool/connections/active", headers=alice_h).json() == {"connection": None}

    for headers in (alice_h, bob_h):
        current = client.get("/api/pool/requests/current", headers=headers).json()
        assert current["connection"] is None
        assert current["ride_ended"] is False

    assert _connection_status(test_session_factory, connection_id) == PoolingConnectionStatus.REJECTED
    assert _request_statuses(test_session_factory, [alice_request_id, bob_request_id]) == {
        alice_request_id: PoolingRequestStatus.MATCHED,
        bob_request_id: PoolingRequestStatus.MATCHED,
    }


def test_partner_cancel_ends_ride_for_the_other_rider(
    client, college, make_user, test_session_factory, ws_sent, fake_distance_matrix
):
    fake_distance_matrix(_fake_distances)
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone=ALICE_PHONE)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone=BOB_PHONE)

    alice_request_id = _create_request(client, alice_h).json()["request_id"]
    bob_request_id = _create_request(client, bob_h).json()["request_id"]
    connection_id = _approve_pair(client, alice_h, bob_h, alice_request_id)

    cancel = client.delete(f"/api/pool/requests/{bob_request_id}", headers=bob_h)
    assert cancel.status_code == 200

    ride_cancelled = _events(ws_sent, alice.id, "ride_cancelled")
    assert len(ride_cancelled) == 1
    assert ride_cancelled[0]["request_id"] == alice_request_id
    assert ride_cancelled[0]["connection_id"] == connection_id
    assert ride_cancelled[0]["by_user"]["id"] == bob.id
    assert _events(ws_sent, bob.id, "ride_cancelled") == []

    _assert_ride_ended(client, alice_h)
    _assert_ride_ended(client, bob_h)
    assert _connection_status(test_session_factory, connection_id) == PoolingConnectionStatus.APPROVED
