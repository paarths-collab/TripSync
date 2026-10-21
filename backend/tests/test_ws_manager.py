"""Unit tests for ConnectionManager using fake websocket objects."""

import asyncio

from app.core.ws_manager import ConnectionManager


class FakeSocket:
    def __init__(self, fail=False):
        self.accepted = False
        self.received = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("socket closed")
        self.received.append(message)


def _run(coro):
    return asyncio.run(coro)


def test_two_sockets_for_one_user_both_receive():
    mgr = ConnectionManager()
    first, second = FakeSocket(), FakeSocket()

    async def scenario():
        await mgr.connect(1, first)
        await mgr.connect(1, second)
        await mgr.send_personal_message({"type": "hello"}, 1)

    _run(scenario())

    assert first.accepted and second.accepted
    assert first.received == [{"type": "hello"}]
    assert second.received == [{"type": "hello"}]


def test_disconnecting_old_socket_keeps_new_socket():
    mgr = ConnectionManager()
    old, new = FakeSocket(), FakeSocket()

    async def scenario():
        await mgr.connect(1, old)
        await mgr.connect(1, new)
        mgr.disconnect(1, old)
        await mgr.send_personal_message({"n": 1}, 1)

    _run(scenario())

    assert old.received == []
    assert new.received == [{"n": 1}]


def test_disconnect_without_socket_removes_all():
    mgr = ConnectionManager()
    a, b = FakeSocket(), FakeSocket()

    async def scenario():
        await mgr.connect(1, a)
        await mgr.connect(1, b)
        mgr.disconnect(1)
        await mgr.send_personal_message({"n": 1}, 1)

    _run(scenario())

    assert a.received == [] and b.received == []
    assert 1 not in mgr.active_connections


def test_failing_socket_does_not_raise_and_is_dropped():
    mgr = ConnectionManager()
    dead, alive = FakeSocket(fail=True), FakeSocket()

    async def scenario():
        await mgr.connect(1, dead)
        await mgr.connect(1, alive)
        await mgr.send_personal_message({"n": 1}, 1)  # must not raise
        await mgr.send_personal_message({"n": 2}, 1)

    _run(scenario())

    assert alive.received == [{"n": 1}, {"n": 2}]
    assert dead not in mgr.active_connections[1]


def test_send_to_unknown_user_is_a_noop():
    mgr = ConnectionManager()
    _run(mgr.send_personal_message({"n": 1}, 999))
