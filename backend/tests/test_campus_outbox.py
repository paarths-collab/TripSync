"""Outbox dispatch for campus party events (fake clock, fake websocket delivery)."""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as app_main
from app.core import campus_rules, campus_time
from app.core.ws_manager import manager
from app.db.database import Base
from app.main import app
from app.models.campus_model import (
    OutboxMessage,
    OutboxStatus,
    PartyEventType,
    TravelParty,
)
from app.services import campus_outbox
from tests.campus_seed import add_event, seed_party


@pytest.fixture
def world(college, make_user, landmarks, make_travel_request, test_session_factory, clock):
    alice, alice_h = make_user("alice@example.test", "Alice Example", college, phone="+10000000001")
    bob, bob_h = make_user("bob@example.test", "Bob Example", college, phone="+10000000002")
    party_id = seed_party(
        test_session_factory, clock, landmarks, make_travel_request, alice, bob
    )
    return {
        "alice": alice, "alice_h": alice_h, "bob": bob, "bob_h": bob_h,
        "party_id": party_id, "factory": test_session_factory,
    }


def _rows(factory, **filters):
    db = factory()
    try:
        rows = db.query(OutboxMessage).filter_by(**filters).order_by(OutboxMessage.id).all()
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


def _party(factory, party_id):
    db = factory()
    try:
        party = db.get(TravelParty, party_id)
        return party.state, party.version
    finally:
        db.close()


def _run(factory, coro_fn, *args, **kwargs):
    db = factory()
    try:
        return asyncio.run(coro_fn(db, *args, **kwargs))
    finally:
        db.close()


# --------------------------------------------------------------------------
# success / failure / retry
# --------------------------------------------------------------------------
def test_dispatch_for_party_delivers_and_marks_sent(world, ws_delivery, clock):
    assert _rows(world["factory"], status=OutboxStatus.PENDING).__len__() == 2

    sent = _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"])

    assert sent == 2
    assert sorted(uid for uid, _ in ws_delivery.sent) == sorted(
        [world["alice"].id, world["bob"].id]
    )
    for _uid, message in ws_delivery.sent:
        assert message == {
            "type": "party_event", "party_id": world["party_id"],
            "version": 1, "event_type": "PARTY_AGREED",
        }
    rows = _rows(world["factory"])
    assert [r.status for r in rows] == [OutboxStatus.SENT, OutboxStatus.SENT]
    assert all(r.sent_at == campus_time.to_db(clock.now) for r in rows)
    assert all(r.attempts == 0 for r in rows)

    # Nothing is re-sent on the next pass.
    assert _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"]) == 0
    assert len(ws_delivery.sent) == 2


def test_failure_records_attempt_backoff_and_error_then_retry_succeeds(world, ws_delivery, clock):
    ws_delivery.fail_all()
    factory = world["factory"]

    assert _run(factory, campus_outbox.dispatch_for_party, world["party_id"]) == 0
    rows = _rows(factory)
    assert [r.status for r in rows] == [OutboxStatus.PENDING] * 2
    assert [r.attempts for r in rows] == [1, 1]
    assert {r.last_error for r in rows} == {"no_live_socket"}
    expected_next = campus_time.to_db(
        clock.now + timedelta(seconds=campus_rules.backoff_seconds(1))
    )
    assert {r.next_attempt_at for r in rows} == {expected_next}
    assert len(ws_delivery.attempts) == 2

    # Not due yet: the backoff is respected (no new delivery attempts).
    clock.advance(seconds=campus_rules.backoff_seconds(1) - 1)
    assert _run(factory, campus_outbox.dispatch_pending) == 0
    assert len(ws_delivery.attempts) == 2

    # Due, still failing: attempts grow and the delay doubles.
    clock.advance(seconds=1)
    assert _run(factory, campus_outbox.dispatch_pending) == 0
    rows = _rows(factory)
    assert [r.attempts for r in rows] == [2, 2]
    assert {r.next_attempt_at for r in rows} == {
        campus_time.to_db(clock.now + timedelta(seconds=campus_rules.backoff_seconds(2)))
    }

    # Socket comes back: the retry delivers and marks the rows SENT.
    ws_delivery.restore()
    clock.advance(seconds=campus_rules.backoff_seconds(2))
    assert _run(factory, campus_outbox.dispatch_pending) == 2
    rows = _rows(factory)
    assert [r.status for r in rows] == [OutboxStatus.SENT] * 2
    assert all(r.sent_at is not None for r in rows)
    assert len(ws_delivery.sent) == 2


def test_one_recipient_failing_does_not_block_the_other(world, ws_delivery):
    ws_delivery.fail_for(world["bob"].id)

    sent = _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"])

    assert sent == 1
    by_user = {r.recipient_id: r for r in _rows(world["factory"])}
    assert by_user[world["alice"].id].status == OutboxStatus.SENT
    assert by_user[world["bob"].id].status == OutboxStatus.PENDING
    assert by_user[world["bob"].id].attempts == 1


def test_rows_become_failed_after_max_attempts_without_touching_party_state(
    world, ws_delivery, clock
):
    ws_delivery.fail_all()
    factory = world["factory"]
    before = _party(factory, world["party_id"])

    for _ in range(campus_rules.OUTBOX_MAX_ATTEMPTS):
        _run(factory, campus_outbox.dispatch_pending)
        clock.advance(seconds=campus_rules.OUTBOX_BACKOFF_MAX_SECONDS + 1)

    rows = _rows(factory)
    assert [r.status for r in rows] == [OutboxStatus.FAILED] * 2
    assert [r.attempts for r in rows] == [campus_rules.OUTBOX_MAX_ATTEMPTS] * 2
    assert {r.last_error for r in rows} == {"no_live_socket"}
    assert len(ws_delivery.attempts) == 2 * campus_rules.OUTBOX_MAX_ATTEMPTS
    assert _party(factory, world["party_id"]) == before

    # FAILED rows are final: even a working socket does not resurrect them.
    ws_delivery.restore()
    assert _run(factory, campus_outbox.dispatch_pending) == 0
    assert [r.status for r in _rows(factory)] == [OutboxStatus.FAILED] * 2


def test_dispatch_pending_honours_limit_and_now(world, ws_delivery, clock):
    factory = world["factory"]
    past = clock.now - timedelta(hours=1)
    assert _run(factory, campus_outbox.dispatch_pending, past) == 0
    assert _run(factory, campus_outbox.dispatch_pending, clock.now, 1) == 1
    assert len(ws_delivery.sent) == 1
    assert _run(factory, campus_outbox.dispatch_pending, clock.now, 5) == 1
    assert len(ws_delivery.sent) == 2


def test_legacy_ws_recorder_returning_none_counts_as_not_delivered(world, ws_sent):
    # The legacy `ws_sent` fixture's fake returns None: treated as 0 sockets.
    assert _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"]) == 0
    rows = _rows(world["factory"])
    assert [r.status for r in rows] == [OutboxStatus.PENDING] * 2
    assert [r.attempts for r in rows] == [1, 1]


def test_dispatch_never_raises_when_manager_errors(world, monkeypatch):
    async def boom(message, user_id):
        raise RuntimeError("socket layer exploded")

    monkeypatch.setattr(manager, "send_personal_message", boom)
    factory = world["factory"]
    before = _party(factory, world["party_id"])

    assert _run(factory, campus_outbox.dispatch_for_party, world["party_id"]) == 0
    assert _run(factory, campus_outbox.dispatch_pending) == 0
    assert _run(factory, campus_outbox.dispatch_for_user, world["alice"].id, force=False) == 0

    rows = _rows(factory)
    assert [r.status for r in rows] == [OutboxStatus.PENDING] * 2
    assert all(r.attempts == 1 for r in rows)  # only the first call was due; later ones backed off
    assert all(r.last_error == "send_error:RuntimeError" for r in rows)
    assert _party(factory, world["party_id"]) == before


def test_one_failing_row_does_not_stop_the_others(world, monkeypatch):
    delivered = []

    async def flaky(message, user_id):
        if user_id == world["alice"].id:
            raise ValueError("bad row")
        delivered.append(user_id)
        return 1

    monkeypatch.setattr(manager, "send_personal_message", flaky)

    assert _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"]) == 1
    assert delivered == [world["bob"].id]


def test_dispatch_swallows_database_errors():
    broken = MagicMock()
    broken.query.side_effect = RuntimeError("db down")
    broken.rollback.side_effect = RuntimeError("rollback failed too")

    assert asyncio.run(campus_outbox.dispatch_for_party(broken, 1)) == 0
    assert asyncio.run(campus_outbox.dispatch_pending(broken)) == 0
    assert asyncio.run(campus_outbox.dispatch_for_user(broken, 1)) == 0


# --------------------------------------------------------------------------
# ack
# --------------------------------------------------------------------------
def test_ack_up_to_marks_only_that_users_rows_up_to_the_version(world, ws_delivery, clock):
    factory = world["factory"]
    add_event(factory, clock, world["party_id"], world["alice"].id)  # v2
    add_event(factory, clock, world["party_id"], world["alice"].id)  # v3
    # Deliver v1..v3 to everyone, then make one row FAILED to prove it is left alone.
    _run(factory, campus_outbox.dispatch_for_party, world["party_id"])
    db = factory()
    try:
        failed = (
            db.query(OutboxMessage)
            .filter(OutboxMessage.recipient_id == world["alice"].id)
            .order_by(OutboxMessage.id.desc())
            .first()
        )
        failed.status = OutboxStatus.FAILED
        db.commit()
        db.expire_all()

        acked = campus_outbox.ack_up_to(db, world["alice"].id, world["party_id"], 2)
    finally:
        db.close()

    assert acked == 2  # alice's v1 and v2; v3 is beyond the version
    rows = _rows(factory)
    versions = {(r.recipient_id, r.payload["version"]): r.status for r in rows}
    alice, bob = world["alice"].id, world["bob"].id
    assert versions[(alice, 1)] == OutboxStatus.ACKED
    assert versions[(alice, 2)] == OutboxStatus.ACKED
    assert versions[(alice, 3)] == OutboxStatus.FAILED  # beyond the acked version
    assert versions[(bob, 1)] == OutboxStatus.SENT  # other user untouched
    assert versions[(bob, 2)] == OutboxStatus.SENT
    assert versions[(bob, 3)] == OutboxStatus.SENT


def test_ack_up_to_covers_pending_and_sent_rows(world, ws_delivery, clock):
    factory = world["factory"]
    add_event(factory, clock, world["party_id"], world["alice"].id)  # v2
    ws_delivery.fail_for(world["alice"].id)
    _run(factory, campus_outbox.dispatch_for_party, world["party_id"])  # alice PENDING, bob SENT

    db = factory()
    try:
        assert campus_outbox.ack_up_to(db, world["alice"].id, world["party_id"], 1) == 1
        assert campus_outbox.ack_up_to(db, world["bob"].id, world["party_id"], 99) == 2
        # Idempotent.
        assert campus_outbox.ack_up_to(db, world["bob"].id, world["party_id"], 99) == 0
    finally:
        db.close()

    rows = _rows(factory)
    state = {(r.recipient_id, r.payload["version"]): r.status for r in rows}
    assert state[(world["alice"].id, 1)] == OutboxStatus.ACKED
    assert state[(world["alice"].id, 2)] == OutboxStatus.PENDING
    assert state[(world["bob"].id, 1)] == OutboxStatus.ACKED
    assert state[(world["bob"].id, 2)] == OutboxStatus.ACKED


def test_acked_rows_are_not_dispatched(world, ws_delivery):
    db = world["factory"]()
    try:
        campus_outbox.ack_up_to(db, world["alice"].id, world["party_id"], 1)
    finally:
        db.close()

    assert _run(world["factory"], campus_outbox.dispatch_for_party, world["party_id"]) == 1
    assert [uid for uid, _ in ws_delivery.sent] == [world["bob"].id]


# --------------------------------------------------------------------------
# concurrency
# --------------------------------------------------------------------------
def test_concurrent_dispatchers_send_each_row_once(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outbox.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    now = datetime(2026, 3, 1, 4, 0, 0)
    n_rows = 24
    db = factory()
    try:
        # FK enforcement is off in SQLite: only the outbox table matters here.
        for i in range(n_rows):
            db.add(
                OutboxMessage(
                    event_id=i + 1, recipient_id=100 + i % 3,
                    payload={"type": "party_event", "party_id": 1, "version": i + 1},
                    status=OutboxStatus.PENDING, attempts=0, next_attempt_at=now, created_at=now,
                )
            )
        db.commit()
    finally:
        db.close()

    sends = []
    lock = threading.Lock()

    async def counting_send(message, user_id):
        await asyncio.sleep(0.005)  # widen the race window
        with lock:
            sends.append((user_id, message["version"]))
        return 1

    monkeypatch.setattr(manager, "send_personal_message", counting_send)

    n_threads = 4
    barrier = threading.Barrier(n_threads)
    results, errors = [], []

    def worker():
        session = factory()
        try:
            barrier.wait()
            results.append(
                asyncio.run(
                    campus_outbox.dispatch_pending(
                        session, datetime_aware(now), limit=100
                    )
                )
            )
        except Exception as exc:  # pragma: no cover - would fail the test below
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    assert len(sends) == n_rows
    assert len(set(sends)) == n_rows  # every row exactly once
    assert sum(results) == n_rows
    db = factory()
    try:
        statuses = [r.status for r in db.query(OutboxMessage).all()]
    finally:
        db.close()
        engine.dispose()
    assert statuses == [OutboxStatus.SENT] * n_rows


def datetime_aware(naive_utc):
    return campus_time.from_db(naive_utc)


def test_claimed_row_is_invisible_to_a_second_dispatcher_until_lease_expires(
    world, ws_delivery, clock
):
    """A dispatcher that crashed mid-send leaves a leased row that becomes due again."""
    factory = world["factory"]
    db = factory()
    try:
        # Simulate a claim by another dispatcher: next_attempt_at pushed into the future.
        lease = campus_time.to_db(clock.now + timedelta(seconds=campus_outbox.CLAIM_LEASE_SECONDS))
        db.query(OutboxMessage).update({"next_attempt_at": lease})
        db.commit()
    finally:
        db.close()

    assert _run(factory, campus_outbox.dispatch_pending) == 0
    clock.advance(seconds=campus_outbox.CLAIM_LEASE_SECONDS)
    assert _run(factory, campus_outbox.dispatch_pending) == 2


# --------------------------------------------------------------------------
# flush on socket connect (accelerator)
# --------------------------------------------------------------------------
def _ws(client, path, headers, auth_jwt):
    return client.websocket_connect(path, subprotocols=["token", auth_jwt(headers)])


@pytest.mark.parametrize("path", ["/api/ws/pool", "/api/ws/chat"])
def test_pending_rows_are_flushed_when_the_socket_connects(world, auth_jwt, path):
    client = TestClient(app)
    factory = world["factory"]

    with _ws(client, path, world["alice_h"], auth_jwt) as ws:
        frame = ws.receive_json()

    assert frame == {
        "type": "party_event", "party_id": world["party_id"],
        "version": 1, "event_type": "PARTY_AGREED",
    }
    by_user = {r.recipient_id: r for r in _rows(factory)}
    assert by_user[world["alice"].id].status == OutboxStatus.SENT
    # Bob never connected: his row waits for the next dispatcher pass.
    assert by_user[world["bob"].id].status == OutboxStatus.PENDING
    assert by_user[world["bob"].id].attempts == 0


def _backoff_rows(factory, clock, **extra):
    db = factory()
    try:
        db.query(OutboxMessage).update(
            {"next_attempt_at": campus_time.to_db(clock.now + timedelta(minutes=5)),
             "attempts": 2, "last_error": "no_live_socket", **extra}
        )
        db.commit()
    finally:
        db.close()


def test_flush_on_connect_ignores_backoff_but_poller_and_party_dispatch_respect_it(
    world, auth_jwt, clock, ws_delivery
):
    factory = world["factory"]
    _backoff_rows(factory, clock)
    # The poller / dispatch_for_party still honour the backoff ...
    assert _run(factory, campus_outbox.dispatch_pending) == 0
    assert _run(factory, campus_outbox.dispatch_for_party, world["party_id"]) == 0
    assert ws_delivery.attempts == []

    # ... but a reconnecting user gets their PENDING rows right away.
    ws_delivery.restore()
    client = TestClient(app)
    with _ws(client, "/api/ws/chat", world["alice_h"], auth_jwt) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

    by_user = {r.recipient_id: r for r in _rows(factory)}
    assert by_user[world["alice"].id].status == OutboxStatus.SENT
    assert by_user[world["alice"].id].last_error is None
    assert by_user[world["bob"].id].status == OutboxStatus.PENDING  # bob is not connected
    assert [uid for uid, _ in ws_delivery.sent] == [world["alice"].id]


def test_flush_on_connect_does_not_take_a_row_leased_by_another_dispatcher(
    world, auth_jwt, clock, ws_delivery
):
    factory = world["factory"]
    _backoff_rows(factory, clock, last_error=campus_outbox.CLAIM_MARK + "someone-else")

    client = TestClient(app)
    with _ws(client, "/api/ws/pool", world["alice_h"], auth_jwt) as ws:
        ws.send_json({"type": "chat_message", "receiver_id": 999999, "content": "x"})
        assert ws.receive_json()["code"] == "not_authorized"

    assert ws_delivery.attempts == []
    assert {r.status for r in _rows(factory)} == {OutboxStatus.PENDING}
    assert {r.attempts for r in _rows(factory)} == {2}


def test_forced_flush_keeps_attempt_and_failed_accounting(world, ws_delivery, clock):
    factory = world["factory"]
    _backoff_rows(factory, clock)
    ws_delivery.fail_all()

    assert _run(factory, campus_outbox.dispatch_for_user, world["alice"].id) == 0
    alice_row = [r for r in _rows(factory) if r.recipient_id == world["alice"].id][0]
    assert alice_row.attempts == 3
    assert alice_row.last_error == "no_live_socket"
    assert alice_row.next_attempt_at == campus_time.to_db(
        clock.now + timedelta(seconds=campus_rules.backoff_seconds(3))
    )

    # Forced attempts count towards FAILED too, and never touch party state.
    before = _party(factory, world["party_id"])
    for _ in range(campus_rules.OUTBOX_MAX_ATTEMPTS):
        _run(factory, campus_outbox.dispatch_for_user, world["alice"].id)
    alice_row = [r for r in _rows(factory) if r.recipient_id == world["alice"].id][0]
    assert alice_row.status == OutboxStatus.FAILED
    assert alice_row.attempts == campus_rules.OUTBOX_MAX_ATTEMPTS
    assert _party(factory, world["party_id"]) == before


def test_flush_on_connect_never_breaks_the_socket(world, auth_jwt, monkeypatch):
    client = TestClient(app)

    async def explode(db, user_id, *a, **kw):
        raise RuntimeError("flush failed")

    monkeypatch.setattr(campus_outbox, "dispatch_for_user", explode)
    with _ws(client, "/api/ws/pool", world["alice_h"], auth_jwt) as ws:
        ws.send_json({"type": "chat_message", "receiver_id": 999999, "content": "hi"})
        # No ride or party with that user: refused, but the socket is alive.
        assert ws.receive_json()["code"] == "not_authorized"


# --------------------------------------------------------------------------
# send timeout
# --------------------------------------------------------------------------
def test_stalled_send_times_out_counts_as_failed_and_does_not_block_others(world, monkeypatch):
    monkeypatch.setattr(campus_outbox, "OUTBOX_SEND_TIMEOUT_SECONDS", 0.05)
    delivered = []

    async def stalled_for_alice(message, user_id):
        if user_id == world["alice"].id:
            await asyncio.sleep(30)
            return 1
        delivered.append(user_id)
        return 1

    monkeypatch.setattr(manager, "send_personal_message", stalled_for_alice)
    factory = world["factory"]
    before = _party(factory, world["party_id"])

    started = time.monotonic()
    sent = _run(factory, campus_outbox.dispatch_for_party, world["party_id"])
    elapsed = time.monotonic() - started

    assert elapsed < 25  # did not wait for the 30s stall
    assert sent == 1
    assert delivered == [world["bob"].id]
    by_user = {r.recipient_id: r for r in _rows(factory)}
    stalled = by_user[world["alice"].id]
    assert stalled.status == OutboxStatus.PENDING
    assert stalled.attempts == 1
    assert stalled.last_error == "send_timeout"
    assert by_user[world["bob"].id].status == OutboxStatus.SENT
    assert _party(factory, world["party_id"]) == before


def test_default_send_timeout_is_five_seconds():
    assert campus_outbox.OUTBOX_SEND_TIMEOUT_SECONDS == 5


# --------------------------------------------------------------------------
# lifespan poller
# --------------------------------------------------------------------------
def test_outbox_poll_seconds_env(monkeypatch):
    monkeypatch.delenv("OUTBOX_POLL_SECONDS", raising=False)
    assert app_main.outbox_poll_seconds() == 5.0
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "0")
    assert app_main.outbox_poll_seconds() == 0
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "0.25")
    assert app_main.outbox_poll_seconds() == 0.25
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "not-a-number")
    assert app_main.outbox_poll_seconds() == 5.0


GUARD_SECONDS = 60  # only a hang guard: tests synchronise on events, never on wall-clock


def test_poll_once_delivers_due_rows(world, ws_delivery):
    asyncio.run(app_main.outbox_poll_once())
    assert len(ws_delivery.sent) == 2
    assert [r.status for r in _rows(world["factory"])] == [OutboxStatus.SENT] * 2


def test_poller_delivers_rows_and_cancels_cleanly(world, monkeypatch):
    both_sent = None  # created inside the running loop
    delivered = []

    async def send(message, user_id):
        delivered.append(user_id)
        if len(delivered) == 2:
            both_sent.set()
        return 1

    monkeypatch.setattr(manager, "send_personal_message", send)

    async def scenario():
        nonlocal both_sent
        both_sent = asyncio.Event()
        task = asyncio.create_task(app_main.run_outbox_poller(0.001))
        await asyncio.wait_for(both_sent.wait(), GUARD_SECONDS)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, GUARD_SECONDS)
        assert task.cancelled()

    asyncio.run(scenario())
    assert sorted(delivered) == sorted([world["alice"].id, world["bob"].id])
    assert [r.status for r in _rows(world["factory"])] == [OutboxStatus.SENT] * 2


def test_poller_survives_dispatch_errors(world, monkeypatch):
    calls = []
    enough = None

    async def failing(db, *a, **kw):
        calls.append(1)
        if len(calls) >= 3:
            enough.set()
        raise RuntimeError("dispatch bug")

    monkeypatch.setattr(campus_outbox, "dispatch_pending", failing)

    async def scenario():
        nonlocal enough
        enough = asyncio.Event()
        task = asyncio.create_task(app_main.run_outbox_poller(0.001))
        await asyncio.wait_for(enough.wait(), GUARD_SECONDS)
        assert not task.done()  # still polling after repeated failures
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, GUARD_SECONDS)

    asyncio.run(scenario())
    assert len(calls) >= 3


def test_lifespan_starts_and_stops_the_poller(world, ws_delivery, monkeypatch):
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "0.05")
    with TestClient(app):
        deadline = time.time() + GUARD_SECONDS  # hang guard only; normally ~0.1s
        while time.time() < deadline and len(ws_delivery.sent) < 2:
            time.sleep(0.02)
    assert len(ws_delivery.sent) == 2
    assert [r.status for r in _rows(world["factory"])] == [OutboxStatus.SENT] * 2


def test_lifespan_poller_disabled_with_zero(world, ws_delivery, monkeypatch):
    started = []

    async def fake_poller(interval):
        started.append(interval)

    monkeypatch.setattr(app_main, "run_outbox_poller", fake_poller)
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "0")
    with TestClient(app):
        pass
    assert started == []
    assert ws_delivery.attempts == []

    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "7")
    with TestClient(app):
        pass
    assert started == [7.0]  # sanity check: the same fake IS used when enabled
