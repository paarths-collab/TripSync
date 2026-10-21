"""Chat / contact access derived from campus party membership.

alice and bob are members of an AGREED party (seeded directly in the DB);
carol is a bystander; dave has a legacy approved pooling connection with alice.
Fictional data only.
"""

import pytest

from app.models.campus_model import PartyEventType, PartyMember, PartyState
from app.models.conversation_model import Conversation
from app.models.message_model import Message
from app.models.pooling_model import PoolingRequest, PoolingRequestStatus
from app.models.profile_model import Profile
from app.services import campus_outbox, connection_access
from tests.campus_seed import end_party, seed_legacy_pair, seed_party

FORBIDDEN = "Chat is only available with an approved ride partner"
PHONES = {"alice": "+10000000001", "bob": "+10000000002", "carol": "+10000000003",
          "dave": "+10000000004"}


@pytest.fixture
def world(college, make_user, landmarks, make_travel_request, test_session_factory, clock):
    users = {}
    for key in ("alice", "bob", "carol", "dave"):
        user, headers = make_user(
            f"{key}@example.test", f"{key.title()} Example", college, phone=PHONES[key]
        )
        users[key] = user
        users[f"{key}_h"] = headers
    db = test_session_factory()
    try:
        db.query(Profile).filter(Profile.user_id == users["alice"].id).update(
            {"year_of_study": "3rd", "bio": "alice bio"}
        )
        db.commit()
    finally:
        db.close()
    users["party_id"] = seed_party(
        test_session_factory, clock, landmarks, make_travel_request, users["alice"], users["bob"]
    )
    # Both clients have "already seen" the agreement, so socket connects do not
    # flush a party_event frame into the chat recorders asserted below.
    db = test_session_factory()
    try:
        for key in ("alice", "bob"):
            campus_outbox.ack_up_to(db, users[key].id, users["party_id"], 1)
    finally:
        db.close()
    users["factory"] = test_session_factory
    users["landmarks"] = landmarks
    users["make_request"] = make_travel_request
    users["clock"] = clock
    return users


def _pool_ws(client, headers, auth_jwt):
    return client.websocket_connect("/api/ws/pool", subprotocols=["token", auth_jwt(headers)])


def _chat_ws(client, headers, auth_jwt):
    return client.websocket_connect("/api/ws/chat", subprotocols=["token", auth_jwt(headers)])


def _count(factory, model):
    db = factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


def _end(world, actor="alice", **kwargs):
    end_party(world["factory"], world["clock"], world["party_id"], world[actor].id, **kwargs)


def _relay(ws, receiver, **extra):
    ws.send_json({"type": "chat_message", "receiver_id": receiver.id, "content": "hello",
                  "created_at": "2030-01-01T00:00:00Z", **extra})


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------
def test_party_members_can_chat_over_rest_while_agreed(client, world):
    found = client.get(
        "/api/chat/conversations/find-or-create",
        params={"partner_id": world["bob"].id}, headers=world["alice_h"],
    )
    assert found.status_code == 200
    conv_id = found.json()["conversation_id"]
    assert found.json()["partner"]["id"] == world["bob"].id

    sent = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["bob"].id, "content": "meet at the gate"},
        headers=world["alice_h"],
    )
    assert sent.status_code == 200
    assert sent.json()["conversation_id"] == conv_id

    reply = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["alice"].id, "content": "on my way"},
        headers=world["bob_h"],
    )
    assert reply.status_code == 200

    history = client.get(f"/api/chat/messages/{conv_id}", headers=world["bob_h"])
    assert [m["content"] for m in history.json()["messages"]] == ["meet at the gate", "on my way"]
    assert client.post(f"/api/chat/messages/{conv_id}/read", headers=world["alice_h"]).status_code == 200


def test_conversation_list_shows_contact_fields_to_party_partner_only(client, world):
    client.post(
        "/api/chat/messages",
        json={"receiver_id": world["bob"].id, "content": "hi"}, headers=world["alice_h"],
    )

    bob_list = client.get("/api/chat/conversations", headers=world["bob_h"]).json()["conversations"]
    partner = bob_list[0]["partner"]
    assert partner["phone_number"] == PHONES["alice"]
    assert partner["email"] == "alice@example.test"
    assert partner["year_of_study"] == "3rd"
    assert partner["bio"] == "alice bio"

    # A bystander sees no conversation and none of the contact data.
    carol_list = client.get("/api/chat/conversations", headers=world["carol_h"])
    assert carol_list.json() == {"conversations": []}
    for secret in ("alice@example.test", PHONES["alice"], "alice bio", PHONES["bob"]):
        assert secret not in carol_list.text


def test_third_user_cannot_create_read_mark_or_send(client, world):
    conv = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["bob"].id, "content": "private"}, headers=world["alice_h"],
    ).json()["conversation_id"]
    before = _count(world["factory"], Message)

    for partner in ("alice", "bob"):
        found = client.get(
            "/api/chat/conversations/find-or-create",
            params={"partner_id": world[partner].id}, headers=world["carol_h"],
        )
        assert found.status_code == 403
        assert found.json()["detail"] == FORBIDDEN
        sent = client.post(
            "/api/chat/messages",
            json={"receiver_id": world[partner].id, "content": "psst"}, headers=world["carol_h"],
        )
        assert sent.status_code == 403
        assert "alice@example.test" not in sent.text and "bob@example.test" not in sent.text

    read = client.get(f"/api/chat/messages/{conv}", headers=world["carol_h"])
    marked = client.post(f"/api/chat/messages/{conv}/read", headers=world["carol_h"])
    assert read.status_code == 403 and "private" not in read.text
    assert marked.status_code == 403
    assert _count(world["factory"], Message) == before
    assert _count(world["factory"], Conversation) == 1


def test_party_member_cannot_chat_with_someone_outside_the_party(client, world):
    # alice is in a party with bob, not with carol.
    resp = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["carol"].id, "content": "hi"}, headers=world["alice_h"],
    )
    assert resp.status_code == 403
    assert _count(world["factory"], Conversation) == 0


@pytest.mark.parametrize(
    "state_kwargs",
    [
        {},  # CANCELLED
        {"state": "COMPLETED", "event_type": "PARTY_COMPLETED", "reason": "completed"},
        {"state": "DISPUTED", "event_type": "PARTY_DISPUTED", "reason": "disputed"},
    ],
    ids=["cancelled", "completed", "disputed"],
)
def test_after_the_party_ends_chat_and_contact_close_but_history_stays(
    client, world, state_kwargs
):
    kwargs = dict(state_kwargs)
    if "state" in kwargs:
        kwargs["state"] = PartyState(kwargs["state"])
        kwargs["event_type"] = PartyEventType(kwargs["event_type"])
    conv = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["bob"].id, "content": "before the end"},
        headers=world["alice_h"],
    ).json()["conversation_id"]
    before = _count(world["factory"], Message)

    _end(world, **kwargs)

    for headers, other in ((world["alice_h"], "bob"), (world["bob_h"], "alice")):
        write = client.post(
            "/api/chat/messages",
            json={"receiver_id": world[other].id, "content": "too late"}, headers=headers,
        )
        assert write.status_code == 403
        found = client.get(
            "/api/chat/conversations/find-or-create",
            params={"partner_id": world[other].id}, headers=headers,
        )
        assert found.status_code == 403
    assert _count(world["factory"], Message) == before

    listing = client.get("/api/chat/conversations", headers=world["bob_h"])
    partner = listing.json()["conversations"][0]["partner"]
    assert partner["full_name"] == "Alice Example"
    assert partner["phone_number"] is None
    assert partner["email"] is None
    assert partner["year_of_study"] is None
    assert partner["bio"] is None
    assert PHONES["alice"] not in listing.text and "alice@example.test" not in listing.text

    # History stays readable to the members.
    history = client.get(f"/api/chat/messages/{conv}", headers=world["bob_h"])
    assert history.status_code == 200
    assert [m["content"] for m in history.json()["messages"]] == ["before the end"]
    assert client.post(f"/api/chat/messages/{conv}/read", headers=world["bob_h"]).status_code == 200
    # ... and still not to a bystander.
    assert client.get(f"/api/chat/messages/{conv}", headers=world["carol_h"]).status_code == 403


def test_inactive_member_row_alone_closes_access(client, world):
    """Defence in depth: an AGREED party does not grant access to a member who left."""
    db = world["factory"]()
    try:
        db.query(PartyMember).filter(PartyMember.user_id == world["bob"].id).update({"active": False})
        db.commit()
    finally:
        db.close()

    resp = client.post(
        "/api/chat/messages",
        json={"receiver_id": world["bob"].id, "content": "hi"}, headers=world["alice_h"],
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# sockets
# --------------------------------------------------------------------------
@pytest.mark.parametrize("opener,sender_key", [(_pool_ws, "pool"), (_chat_ws, "chat")])
def test_sockets_relay_between_party_members_with_party_id(
    client, world, ws_sent, auth_jwt, opener, sender_key
):
    with opener(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["bob"])
        _relay(ws, world["bob"], party_id=world["party_id"])
        _relay(ws, world["bob"], party_id=str(world["party_id"]))
        ws.send_json([])  # round-trip: all previous frames have been processed
        assert ws.receive_json()["type"] == "error"

    assert len(ws_sent) == 3
    for uid, message in ws_sent:
        assert uid == world["bob"].id
        assert message["party_id"] == world["party_id"]
        assert "connection_id" not in message
        assert message["type"] == "chat_message"
        assert message["sender_id"] == world["alice"].id
        assert message["content"] == "hello"
        assert message["created_at"] == "2030-01-01T00:00:00Z"
    if sender_key == "pool":
        assert ws_sent[0][1]["sender_name"] == "Alice Example"


@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
def test_sockets_refuse_a_third_user(client, world, ws_sent, auth_jwt, opener):
    with opener(client, world["carol_h"], auth_jwt) as ws:
        for receiver in (world["alice"], world["bob"]):
            _relay(ws, receiver, party_id=world["party_id"])
            frame = ws.receive_json()
            assert frame["type"] == "error"
            assert frame["code"] == "not_authorized"
            assert frame["detail"] == FORBIDDEN
    assert ws_sent == []


@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
@pytest.mark.parametrize(
    "extra",
    [
        {"party_id": 987654},                      # not their party
        {"party_id": True},                        # bool masquerading as 1
        {"party_id": "abc"},                       # garbage
        {"party_id": [1]},
        {"party_id": 0},
        {"connection_id": 1},                      # no legacy connection exists
        {"connection_id": "1"},
        {"party_id": 1, "connection_id": 1},  # real party id, but no such legacy connection
    ],
    ids=lambda e: ",".join(f"{k}={v!r}" for k, v in e.items()),
)
def test_sockets_refuse_wrong_client_supplied_ids(client, world, ws_sent, auth_jwt, opener, extra):
    # NB: the seeded party is id 1, so party_id=True (== 1 in Python) must still be refused.
    with opener(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["bob"], **extra)
        frame = ws.receive_json()
    assert frame["code"] == "not_authorized"
    assert ws_sent == []


@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
def test_sockets_reject_self_and_garbage_receivers(client, world, ws_sent, auth_jwt, opener):
    with opener(client, world["alice_h"], auth_jwt) as ws:
        for receiver in (world["alice"].id, True, "bob", 987654, [world["bob"].id]):
            ws.send_json({"type": "chat_message", "receiver_id": receiver, "content": "x"})
            assert ws.receive_json()["code"] == "not_authorized"
    assert ws_sent == []


@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
def test_socket_rechecks_party_state_per_message(client, world, ws_sent, auth_jwt, opener):
    with opener(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["bob"])
        ws.send_json({"type": "chat_message", "receiver_id": 987654, "content": "sync"})
        assert ws.receive_json()["code"] == "not_authorized"  # first relay was processed
        assert len(ws_sent) == 1

        _end(world)  # party cancelled while the socket stays open

        _relay(ws, world["bob"])
        frame = ws.receive_json()
        assert frame["code"] == "not_authorized"
        _relay(ws, world["bob"], party_id=world["party_id"])
        assert ws.receive_json()["code"] == "not_authorized"
    assert len(ws_sent) == 1


@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
def test_tokens_are_never_echoed(client, world, ws_sent, auth_jwt, opener):
    token = auth_jwt(world["alice_h"])
    with opener(client, world["alice_h"], auth_jwt) as ws:
        assert ws.accepted_subprotocol == "token"
        _relay(ws, world["carol"])
        frame = ws.receive_json()
        _relay(ws, world["bob"])
        ws.send_json([])
        error = ws.receive_json()
    assert token not in str(frame) and token not in str(error)
    assert all(token not in str(message) for _, message in ws_sent)


# --------------------------------------------------------------------------
# legacy pooling pair is unchanged / mixed users
# --------------------------------------------------------------------------
@pytest.mark.parametrize("opener", [_pool_ws, _chat_ws])
def test_legacy_pair_is_authorized_exactly_as_before(client, world, ws_sent, auth_jwt, opener):
    conn_id, _ = seed_legacy_pair(world["factory"], world["alice"], world["dave"])

    with opener(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["dave"], connection_id=conn_id)
        _relay(ws, world["dave"])  # connection_id optional, as before
        _relay(ws, world["dave"], connection_id=conn_id + 100)  # wrong id refused
        assert ws.receive_json()["code"] == "not_authorized"
        _relay(ws, world["dave"], party_id=world["party_id"])  # no such party between them
        assert ws.receive_json()["code"] == "not_authorized"

    assert [uid for uid, _ in ws_sent] == [world["dave"].id, world["dave"].id]
    for _, message in ws_sent:
        assert message["connection_id"] == conn_id
        assert "party_id" not in message


def test_user_in_a_legacy_ride_and_a_party_chats_with_both_partners(client, world):
    seed_legacy_pair(world["factory"], world["alice"], world["dave"])

    for partner in ("bob", "dave"):
        resp = client.post(
            "/api/chat/messages",
            json={"receiver_id": world[partner].id, "content": f"hi {partner}"},
            headers=world["alice_h"],
        )
        assert resp.status_code == 200, partner
    listing = client.get("/api/chat/conversations", headers=world["alice_h"]).json()["conversations"]
    by_id = {c["partner"]["id"]: c["partner"] for c in listing}
    assert by_id[world["bob"].id]["phone_number"] == PHONES["bob"]
    assert by_id[world["dave"].id]["phone_number"] == PHONES["dave"]

    # Party ends: only the legacy partner stays reachable.
    _end(world)
    assert client.post(
        "/api/chat/messages", json={"receiver_id": world["bob"].id, "content": "x"},
        headers=world["alice_h"],
    ).status_code == 403
    assert client.post(
        "/api/chat/messages", json={"receiver_id": world["dave"].id, "content": "x"},
        headers=world["alice_h"],
    ).status_code == 200
    listing = client.get("/api/chat/conversations", headers=world["alice_h"]).json()["conversations"]
    by_id = {c["partner"]["id"]: c["partner"] for c in listing}
    assert by_id[world["bob"].id]["phone_number"] is None
    assert by_id[world["dave"].id]["phone_number"] == PHONES["dave"]


def test_same_pair_with_both_a_legacy_ride_and_a_party(client, world, ws_sent, auth_jwt):
    conn_id, req_ids = seed_legacy_pair(world["factory"], world["alice"], world["bob"])
    with _chat_ws(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["bob"])                                    # no hint: legacy
        _relay(ws, world["bob"], party_id=world["party_id"])        # party named: party
        _relay(ws, world["bob"], connection_id=conn_id)             # connection named: legacy
        _relay(ws, world["bob"], connection_id=conn_id, party_id=world["party_id"])
        _relay(ws, world["bob"], connection_id=conn_id + 100)       # wrong connection
        assert ws.receive_json()["code"] == "not_authorized"
        _relay(ws, world["bob"], party_id=world["party_id"] + 100)  # wrong party
        assert ws.receive_json()["code"] == "not_authorized"

    refs = [({k: m[k] for k in ("connection_id", "party_id") if k in m}) for _, m in ws_sent]
    assert refs == [
        {"connection_id": conn_id},
        {"party_id": world["party_id"]},
        {"connection_id": conn_id},
        {"connection_id": conn_id},
    ]

    # Legacy ride ends: the party still grants access.
    db = world["factory"]()
    try:
        db.query(PoolingRequest).filter(PoolingRequest.id.in_(req_ids)).update(
            {"status": PoolingRequestStatus.CANCELLED}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
    ws_sent.clear()
    with _chat_ws(client, world["alice_h"], auth_jwt) as ws:
        _relay(ws, world["bob"])
        _relay(ws, world["bob"], connection_id=conn_id)  # legacy grant is gone
        assert ws.receive_json()["code"] == "not_authorized"
    assert [{k: m[k] for k in ("connection_id", "party_id") if k in m} for _, m in ws_sent] == [
        {"party_id": world["party_id"]}
    ]


# --------------------------------------------------------------------------
# connection_access unit behaviour
# --------------------------------------------------------------------------
def test_connection_access_helpers(world):
    db = world["factory"]()
    try:
        alice, bob, carol = world["alice"].id, world["bob"].id, world["carol"].id
        assert connection_access.users_have_active_ride(db, alice, bob)
        assert connection_access.users_have_active_ride(db, bob, alice)
        assert not connection_access.users_have_active_ride(db, alice, carol)
        assert not connection_access.users_have_active_ride(db, alice, alice)
        assert not connection_access.users_have_active_ride(db, alice, None)
        assert connection_access.get_active_partner_ids(db, alice) == {bob}
        assert connection_access.get_active_partner_ids(db, carol) == set()
        party = connection_access.get_active_ride_connection(db, alice, bob)
        assert party.id == world["party_id"]

        grant = connection_access.authorize_relay(db, alice, bob)
        assert grant.id == world["party_id"]
        assert connection_access.authorize_relay(db, alice, str(bob), party_id=str(party.id)).id == party.id
        assert connection_access.authorize_relay(db, alice, alice) is None
        assert connection_access.authorize_relay(db, alice, True) is None
        assert connection_access.authorize_relay(db, alice, "1.5") is None
        assert connection_access.authorize_relay(db, alice, bob, party_id=False) is None
        assert connection_access.authorize_relay(db, alice, bob, party_id=party.id + 1) is None
        assert connection_access.authorize_relay(db, alice, bob, connection_id=party.id) is None
        assert connection_access.authorize_relay(db, carol, bob) is None
    finally:
        db.close()

    _end(world)
    db = world["factory"]()
    try:
        assert not connection_access.users_have_active_ride(db, world["alice"].id, world["bob"].id)
        assert connection_access.get_active_partner_ids(db, world["alice"].id) == set()
        assert connection_access.authorize_relay(db, world["alice"].id, world["bob"].id) is None
    finally:
        db.close()
