"""Tests for the synthetic demo seed/reset script (scripts/seed_demo.py)."""

import pytest

from app.db import database as app_database
from app.models import conversation_model, message_model, pooling_model, profile_model, user_model
from app.services.user_service import verify_password
from scripts import seed_demo as demo

PASSWORD = "demo-password-test-only"


def _seeded_ids(session_factory):
    db = session_factory()
    try:
        return [u.id for u in demo.seed_demo(db, PASSWORD)]
    finally:
        db.close()


def test_seed_twice_creates_exactly_two_demo_users_and_one_college(test_session_factory):
    db = test_session_factory()
    try:
        first = [u.id for u in demo.seed_demo(db, PASSWORD)]
        second = [u.id for u in demo.seed_demo(db, PASSWORD)]

        assert len(first) == 2
        assert first == second
        assert db.query(user_model.User).count() == 2
        assert db.query(user_model.College).count() == 1
        college = db.query(user_model.College).one()
        assert college.name == demo.DEMO_COLLEGE_NAME

        users = db.query(user_model.User).order_by(user_model.User.email).all()
        assert [u.email for u in users] == ["demo-rider-a@example.test", "demo-rider-b@example.test"]
        assert [u.full_name for u in users] == ["Demo Rider A (demo)", "Demo Rider B (demo)"]
        assert all(u.college_id == college.id for u in users)

        phones = {
            p.user_id: p.phone_number
            for p in db.query(profile_model.Profile).all()
        }
        assert sorted(phones.values()) == ["+10000000001", "+10000000002"]
        assert db.query(profile_model.Profile).count() == 2
    finally:
        db.close()


def test_seed_reuses_existing_college_with_same_name(test_session_factory):
    db = test_session_factory()
    try:
        existing = user_model.College(name="DJSCE")
        db.add(existing)
        db.commit()
        existing_id = existing.id

        demo.seed_demo(db, PASSWORD)

        assert db.query(user_model.College).count() == 1
        assert {u.college_id for u in db.query(user_model.User).all()} == {existing_id}
    finally:
        db.close()


def test_seeded_password_is_bcrypt_hashed_and_verifies(test_session_factory):
    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        for user in db.query(user_model.User).all():
            assert user.hashed_password != PASSWORD
            assert user.hashed_password.startswith("$2")
            assert verify_password(PASSWORD, user.hashed_password)
            assert not verify_password("wrong-password-value", user.hashed_password)
    finally:
        db.close()


def test_reset_removes_only_demo_data_and_keeps_other_users(test_session_factory, make_user, college):
    alice, _ = make_user("alice@example.test", "Alice Example", college, phone="+10000000003")
    bob, _ = make_user("bob@example.test", "Bob Example", college, phone="+10000000004")
    demo_a_id, demo_b_id = _seeded_ids(test_session_factory)

    db = test_session_factory()
    try:
        def request(user_id):
            row = pooling_model.PoolingRequest(
                user_id=user_id,
                start_latitude=19.07,
                start_longitude=72.87,
                destination_latitude=19.13,
                destination_longitude=72.83,
            )
            db.add(row)
            db.flush()
            return row

        demo_req_a = request(demo_a_id)
        demo_req_b = request(demo_b_id)
        other_req = request(alice.id)
        db.add(
            pooling_model.PoolingConnection(
                sender_request_id=other_req.id,
                receiver_request_id=demo_req_a.id,
            )
        )

        demo_conv = conversation_model.Conversation(user1_id=demo_a_id, user2_id=demo_b_id)
        other_conv = conversation_model.Conversation(user1_id=alice.id, user2_id=bob.id)
        db.add_all([demo_conv, other_conv])
        db.flush()
        db.add_all(
            [
                message_model.Message(conversation_id=demo_conv.id, sender_id=demo_a_id, content="hi"),
                message_model.Message(conversation_id=demo_conv.id, sender_id=demo_b_id, content="hello"),
                message_model.Message(conversation_id=other_conv.id, sender_id=alice.id, content="keep me"),
            ]
        )
        db.commit()
        other_req_id = other_req.id
        other_conv_id = other_conv.id
    finally:
        db.close()

    db = test_session_factory()
    try:
        counts = demo.reset_demo(db)

        assert counts == {
            "messages": 2,
            "conversations": 1,
            "pooling_connections": 1,
            "pooling_requests": 2,
        }
        assert db.query(user_model.User).count() == 4
        assert {u.id for u in db.query(user_model.User).filter(user_model.User.email.in_(demo.DEMO_EMAILS))} == {
            demo_a_id,
            demo_b_id,
        }
        assert [r.id for r in db.query(pooling_model.PoolingRequest).all()] == [other_req_id]
        assert db.query(pooling_model.PoolingConnection).count() == 0
        assert [c.id for c in db.query(conversation_model.Conversation).all()] == [other_conv_id]
        assert [m.content for m in db.query(message_model.Message).all()] == ["keep me"]

        # A second reset finds nothing left to delete.
        assert demo.reset_demo(db) == {
            "messages": 0,
            "conversations": 0,
            "pooling_connections": 0,
            "pooling_requests": 0,
        }
    finally:
        db.close()


def test_main_exits_nonzero_without_demo_password(monkeypatch, capsys):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)

    with pytest.raises(SystemExit) as exc:
        demo.main([])

    assert exc.value.code != 0
    assert "DEMO_PASSWORD" in capsys.readouterr().err


def test_main_exits_nonzero_for_short_demo_password_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setenv("DEMO_PASSWORD", "x7short")

    with pytest.raises(SystemExit) as exc:
        demo.main(["--reset"])

    captured = capsys.readouterr()
    assert exc.value.code != 0
    assert "x7short" not in captured.out + captured.err


def test_main_seeds_then_resets_through_cli_argv(monkeypatch, test_engine, test_session_factory, capsys):
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    monkeypatch.setattr(app_database, "engine", test_engine)

    assert demo.main([]) == 0
    db = test_session_factory()
    try:
        assert db.query(user_model.User).count() == 2
    finally:
        db.close()

    assert demo.main(["--reset"]) == 0
    out = capsys.readouterr().out
    assert "Demo reset complete" in out
    assert PASSWORD not in out
    db = test_session_factory()
    try:
        assert db.query(user_model.User).count() == 2  # demo users themselves are kept
    finally:
        db.close()
