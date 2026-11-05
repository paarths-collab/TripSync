"""Tests for the synthetic demo seed/reset script (scripts/seed_demo.py)."""

from datetime import datetime, timezone

import pytest

from app.core import campus_rules, campus_time
from app.db import database as app_database
from app.models import (
    campus_model,
    conversation_model,
    message_model,
    pooling_model,
    profile_model,
    user_model,
)
from app.services.user_service import verify_password
from scripts import seed_demo as demo

PASSWORD = "demo-password-test-only"
LEGACY_KEYS = ("messages", "conversations", "pooling_connections", "pooling_requests")


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

        assert {k: counts[k] for k in LEGACY_KEYS} == {
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
        assert set(demo.reset_demo(db).values()) == {0}
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


# --------------------------------------------------------------------------
# campus landmarks + demo requests
# --------------------------------------------------------------------------
def _campus_state(db):
    landmarks = db.query(campus_model.CampusLandmark).order_by(campus_model.CampusLandmark.id).all()
    requests = db.query(campus_model.TravelRequest).order_by(campus_model.TravelRequest.id).all()
    return landmarks, requests


def test_seed_creates_demo_landmarks_and_two_open_requests(clock, test_session_factory):
    # clock: 2026-03-01T04:00Z = 09:30 IST -> next local day is 2026-03-02
    db = test_session_factory()
    try:
        users = demo.seed_demo(db, PASSWORD)
        landmarks, requests = _campus_state(db)

        assert {(l.name, l.kind) for l in landmarks} == {
            ("Main Gate", campus_model.LandmarkKind.CAMPUS_POINT),
            ("Airport Terminal", campus_model.LandmarkKind.HUB),
        }
        assert all(l.college_id == users[0].college_id and l.active for l in landmarks)
        assert all(-90 <= l.latitude <= 90 and -180 <= l.longitude <= 180 for l in landmarks)

        assert len(requests) == 2
        by_user = {r.user_id: r for r in requests}
        a, b = by_user[users[0].id], by_user[users[1].id]
        gate = next(l for l in landmarks if l.name == "Main Gate")
        terminal = next(l for l in landmarks if l.name == "Airport Terminal")
        for r in (a, b):
            assert r.status == campus_model.TravelRequestStatus.OPEN and r.version == 1
            assert r.direction == campus_model.Direction.TO_HUB
            assert (r.origin_landmark_id, r.hub_id) == (gate.id, terminal.id)
            assert r.flexibility_consent is False and r.arrive_by is None
            assert r.timezone == "Asia/Kolkata" and r.college_id == users[0].college_id
            assert r.expires_at == r.latest_departure
        local = lambda dt: campus_time.local_iso(campus_time.from_db(dt), "Asia/Kolkata")
        assert (local(a.earliest_departure), local(a.latest_departure)) == (
            "2026-03-02T18:00:00+05:30", "2026-03-02T19:00:00+05:30")
        assert (local(b.earliest_departure), local(b.latest_departure)) == (
            "2026-03-02T18:30:00+05:30", "2026-03-02T19:30:00+05:30")

        # the riders are a valid suggestion for each other
        verdict = campus_rules.eligible_pair(a, b, clock.now)
        assert verdict.ok and verdict.reason == "WINDOW_OVERLAP"
    finally:
        db.close()


def test_seed_twice_does_not_duplicate_landmarks_or_requests(clock, test_session_factory):
    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        demo.seed_demo(db, PASSWORD)
        landmarks, requests = _campus_state(db)
        assert len(landmarks) == 2 and len(requests) == 2
        assert [r.version for r in requests] == [1, 1]   # unchanged windows -> untouched
    finally:
        db.close()


def test_reseeding_later_moves_the_open_requests_to_the_new_next_day(clock, test_session_factory):
    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        clock.advance(days=2)
        demo.seed_demo(db, PASSWORD)
        _, requests = _campus_state(db)
        assert len(requests) == 2
        assert {campus_time.local_iso(campus_time.from_db(r.earliest_departure), "Asia/Kolkata")[:10]
                for r in requests} == {"2026-03-04"}
        assert all(r.version == 2 and r.status == campus_model.TravelRequestStatus.OPEN for r in requests)
    finally:
        db.close()


def test_next_day_is_computed_in_campus_local_time(clock, test_session_factory):
    # 2026-03-01T19:00Z is already 00:30 IST on March 2, so "next day" is March 3.
    clock.set(datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc))
    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        _, requests = _campus_state(db)
        starts = sorted(campus_time.local_iso(campus_time.from_db(r.earliest_departure), "Asia/Kolkata")
                        for r in requests)
        assert starts == ["2026-03-03T18:00:00+05:30", "2026-03-03T18:30:00+05:30"]
    finally:
        db.close()


def test_seed_leaves_a_reserved_demo_request_alone(clock, test_session_factory):
    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        _, requests = _campus_state(db)
        requests[0].status = campus_model.TravelRequestStatus.RESERVED
        db.commit()
        demo.seed_demo(db, PASSWORD)
        _, requests = _campus_state(db)
        assert len(requests) == 2
        assert requests[0].status == campus_model.TravelRequestStatus.RESERVED
    finally:
        db.close()


# --------------------------------------------------------------------------
# reset of campus data
# --------------------------------------------------------------------------
def _campus_request(db, user_id, college_id, gate, terminal, clock, status="OPEN", minutes=(60, 120)):
    row = campus_model.TravelRequest(
        user_id=user_id, college_id=college_id,
        mode=campus_model.TravelMode.SHARED_TAXI_PARTY,
        origin_landmark_id=gate.id, hub_id=terminal.id,
        direction=campus_model.Direction.TO_HUB,
        earliest_departure=campus_time.to_db(clock.at(minutes=minutes[0])),
        latest_departure=campus_time.to_db(clock.at(minutes=minutes[1])),
        timezone="Asia/Kolkata", flexibility_consent=False,
        expires_at=campus_time.to_db(clock.at(minutes=minutes[1])),
        status=campus_model.TravelRequestStatus(status), version=1,
    )
    db.add(row)
    db.flush()
    return row


def _suggestion(db, a, b, clock):
    low, high = campus_rules.pair_key(a.id, b.id)
    now = campus_time.to_db(clock.now)
    row = campus_model.PairSuggestion(
        request_low_id=low, request_high_id=high, rule_version=campus_rules.RULE_VERSION,
        reason=campus_model.SuggestionReason.WINDOW_OVERLAP, feasible_start=now, feasible_end=now,
        estimate_status=campus_model.EstimateStatus.UNVERIFIED, warnings=[], valid_until=now,
    )
    db.add(row)
    db.flush()
    return row


def _proposal(db, proposer, recipient, req_p, req_r, clock, suggestion=None, state="PENDING", party=None):
    row = campus_model.ConnectionProposal(
        suggestion_id=suggestion.id if suggestion else None,
        proposer_id=proposer, recipient_id=recipient,
        proposer_request_id=req_p.id, recipient_request_id=req_r.id,
        proposer_request_version=1, recipient_request_version=1,
        state=campus_model.ProposalState(state),
        expires_at=campus_time.to_db(clock.at(minutes=30)),
        party_id=party.id if party else None,
    )
    db.add(row)
    db.flush()
    return row


def _party(db, members, gate, terminal, clock):
    """members: list of (user_id, request) -> a TravelParty with members, an event, outbox rows."""
    party = campus_model.TravelParty(
        state=campus_model.PartyState.AGREED,
        agreed_departure=campus_time.to_db(clock.at(minutes=60)),
        meeting_landmark_id=gate.id, hub_id=terminal.id,
        direction=campus_model.Direction.TO_HUB, timezone="Asia/Kolkata",
        transport_responsibility=campus_rules.TRANSPORT_RESPONSIBILITY_TEXT, version=1,
    )
    db.add(party)
    db.flush()
    for user_id, request in members:
        db.add(campus_model.PartyMember(party_id=party.id, user_id=user_id, request_id=request.id, active=True))
    event = campus_model.PartyEvent(
        party_id=party.id, version=1, actor_id=members[0][0], event_type="PARTY_AGREED", payload={})
    db.add(event)
    db.flush()
    for user_id, _ in members:
        db.add(campus_model.OutboxMessage(
            event_id=event.id, recipient_id=user_id, payload={"type": "party_event"},
            next_attempt_at=campus_time.to_db(clock.now)))
    db.add(campus_model.PartyChangeProposal(
        party_id=party.id, proposer_id=members[0][0], expected_party_version=1,
        new_departure=campus_time.to_db(clock.at(minutes=90))))
    db.add(campus_model.IdempotencyRecord(
        user_id=members[-1][0], operation="accept_connection", key=f"k-{party.id}",
        target_id=party.id, response_status=200, response_body={}))
    db.flush()
    return party


def test_reset_deletes_demo_campus_data_only(clock, test_session_factory, make_user, college):
    alice, _ = make_user("alice@example.test", "Alice Example", college)
    bob, _ = make_user("bob@example.test", "Bob Example", college)
    demo_a_id, demo_b_id = _seeded_ids(test_session_factory)

    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)           # landmarks + the two demo requests
        gate = db.query(campus_model.CampusLandmark).filter_by(name="Main Gate").one()
        terminal = db.query(campus_model.CampusLandmark).filter_by(name="Airport Terminal").one()
        demo_req = {r.user_id: r for r in db.query(campus_model.TravelRequest).all()}
        da, dbb = demo_req[demo_a_id], demo_req[demo_b_id]

        alice_req = _campus_request(db, alice.id, college.id, gate, terminal, clock, minutes=(300, 360))
        alice_party_req = _campus_request(db, alice.id, college.id, gate, terminal, clock,
                                          status="RESERVED", minutes=(400, 460))
        bob_req = _campus_request(db, bob.id, college.id, gate, terminal, clock, minutes=(300, 360))
        bob_party_req = _campus_request(db, bob.id, college.id, gate, terminal, clock,
                                        status="RESERVED", minutes=(500, 560))
        carol_like = _campus_request(db, alice.id, college.id, gate, terminal, clock,
                                     status="CANCELLED", minutes=(600, 660))

        # demo-related rows
        s_demo = _suggestion(db, da, dbb, clock)
        s_mixed = _suggestion(db, da, alice_req, clock)
        _proposal(db, demo_a_id, demo_b_id, da, dbb, clock, suggestion=s_demo)
        mixed_party_prop = _proposal(db, alice.id, demo_a_id, alice_party_req, da, clock, state="ACCEPTED")
        # bind a mixed party: alice (non-demo) + demo A
        mixed_party = _party(db, [(demo_a_id, da), (alice.id, alice_party_req)], gate, terminal, clock)
        mixed_party_prop.party_id = mixed_party.id
        demo_only_party = _party(db, [(demo_b_id, dbb)], gate, terminal, clock)

        # rows that must survive: a pair of non-demo users
        s_other = _suggestion(db, alice_req, bob_req, clock)
        p_other = _proposal(db, alice.id, bob.id, alice_req, bob_req, clock, suggestion=s_other)
        other_party = _party(db, [(bob.id, bob_party_req)], gate, terminal, clock)
        db.commit()
        ids = dict(alice_req=alice_req.id, bob_req=bob_req.id, carol_like=carol_like.id,
                   alice_party_req=alice_party_req.id, bob_party_req=bob_party_req.id,
                   s_other=s_other.id, p_other=p_other.id, other_party=other_party.id,
                   gate=gate.id, terminal=terminal.id)
        deleted_ids = dict(da=da.id, dbb=dbb.id, s_demo=s_demo.id, s_mixed=s_mixed.id,
                           mixed_party=mixed_party.id, demo_only_party=demo_only_party.id)
    finally:
        db.close()

    db = test_session_factory()
    try:
        counts = demo.reset_demo(db)
        assert counts["campus_requests"] == 2
        assert counts["campus_suggestions"] == 2
        assert counts["campus_proposals"] == 2
        assert counts["campus_parties"] == 2
        assert counts["campus_party_members"] == 3
        assert counts["campus_events"] == 2
        assert counts["campus_outbox"] == 3       # 2 (mixed party) + 1 (demo-only party)
        assert counts["campus_idempotency"] == 1   # records are removed per demo user, not per target

        cm = campus_model
        assert {r.id for r in db.query(cm.TravelRequest).all()} == {
            ids["alice_req"], ids["bob_req"], ids["carol_like"], ids["alice_party_req"], ids["bob_party_req"]}
        assert db.query(cm.PairSuggestion).one().id == ids["s_other"]
        assert db.query(cm.ConnectionProposal).one().id == ids["p_other"]
        assert db.query(cm.TravelParty).one().id == ids["other_party"]
        assert db.query(cm.PartyMember).count() == 1
        assert db.query(cm.PartyEvent).count() == 1
        assert db.query(cm.OutboxMessage).count() == 1
        assert db.query(cm.PartyChangeProposal).count() == 1
        # landmarks and users stay
        assert {l.id for l in db.query(cm.CampusLandmark).all()} == {ids["gate"], ids["terminal"]}
        assert db.query(user_model.User).count() == 4
        # a non-demo request held by a deleted party is released like a party cancel
        # (still valid -> OPEN); the unrelated party's request is untouched
        assert db.get(cm.TravelRequest, ids["alice_party_req"]).status == cm.TravelRequestStatus.OPEN
        assert db.get(cm.TravelRequest, ids["alice_party_req"]).version == 2
        assert db.get(cm.TravelRequest, ids["bob_party_req"]).status == cm.TravelRequestStatus.RESERVED
        assert db.get(cm.TravelRequest, ids["alice_req"]).status == cm.TravelRequestStatus.OPEN
        assert db.get(cm.TravelRequest, ids["alice_req"]).version == 1

        # second reset is a no-op, and re-seeding restores a clean demo
        assert set(demo.reset_demo(db).values()) == {0}
        demo.seed_demo(db, PASSWORD)
        assert db.query(cm.TravelRequest).filter(cm.TravelRequest.user_id.in_([demo_a_id, demo_b_id])).count() == 2
    finally:
        db.close()


def test_reset_removes_the_seeded_demo_requests_but_keeps_landmarks(clock, test_session_factory):
    _seeded_ids(test_session_factory)
    db = test_session_factory()
    try:
        counts = demo.reset_demo(db)
        assert counts["campus_requests"] == 2 and counts["campus_parties"] == 0
        assert db.query(campus_model.TravelRequest).count() == 0
        assert db.query(campus_model.CampusLandmark).count() == 2
    finally:
        db.close()


def test_reset_releases_non_demo_requests_open_if_valid_else_expired(
    clock, test_session_factory, make_user, college
):
    alice, _ = make_user("alice@example.test", "Alice Example", college)
    bob, _ = make_user("bob@example.test", "Bob Example", college)
    demo_a_id, demo_b_id = _seeded_ids(test_session_factory)

    db = test_session_factory()
    try:
        demo.seed_demo(db, PASSWORD)
        gate = db.query(campus_model.CampusLandmark).filter_by(name="Main Gate").one()
        terminal = db.query(campus_model.CampusLandmark).filter_by(name="Airport Terminal").one()
        demo_req = {r.user_id: r for r in db.query(campus_model.TravelRequest).all()}
        short = _campus_request(db, alice.id, college.id, gate, terminal, clock,
                                status="RESERVED", minutes=(10, 60))
        long_ = _campus_request(db, bob.id, college.id, gate, terminal, clock,
                                status="RESERVED", minutes=(10, 600))
        _party(db, [(demo_a_id, demo_req[demo_a_id]), (alice.id, short)], gate, terminal, clock)
        _party(db, [(demo_b_id, demo_req[demo_b_id]), (bob.id, long_)], gate, terminal, clock)
        db.commit()
        short_id, long_id = short.id, long_.id
        bob_before = (long_.user_id, long_.earliest_departure, long_.latest_departure, long_.expires_at)
    finally:
        db.close()

    clock.advance(minutes=120)   # alice's request has now ended; bob's is still valid
    db = test_session_factory()
    try:
        assert demo.reset_demo(db)["campus_parties"] == 2
        cm = campus_model
        short = db.get(cm.TravelRequest, short_id)
        long_ = db.get(cm.TravelRequest, long_id)
        assert short.status == cm.TravelRequestStatus.EXPIRED and short.version == 2
        assert long_.status == cm.TravelRequestStatus.OPEN and long_.version == 2
        # nothing else about the non-demo request changed
        assert (long_.user_id, long_.earliest_departure, long_.latest_departure, long_.expires_at) == bob_before
        # no non-demo user-owned rows were deleted
        assert db.query(user_model.User).count() == 4
        assert {r.id for r in db.query(cm.TravelRequest).all()} == {short_id, long_id}
    finally:
        db.close()


def test_seed_never_clobbers_an_existing_landmark_with_the_same_name(clock, test_session_factory):
    db = test_session_factory()
    try:
        college = user_model.College(name=demo.DEMO_COLLEGE_NAME)
        db.add(college)
        db.flush()
        gate = campus_model.CampusLandmark(
            college_id=college.id, name="Main Gate", kind=campus_model.LandmarkKind.CAMPUS_POINT,
            latitude=1.5, longitude=2.5, timezone="Asia/Tokyo", active=False)
        terminal = campus_model.CampusLandmark(
            college_id=college.id, name="Airport Terminal", kind=campus_model.LandmarkKind.HUB,
            latitude=3.5, longitude=4.5, timezone="Asia/Tokyo", active=True)
        db.add_all([gate, terminal])
        db.commit()
        gate_id, terminal_id = gate.id, terminal.id

        demo.seed_demo(db, PASSWORD)
        demo.seed_demo(db, PASSWORD)

        landmarks = db.query(campus_model.CampusLandmark).order_by(campus_model.CampusLandmark.id).all()
        assert [l.id for l in landmarks] == [gate_id, terminal_id]       # nothing added
        g = db.get(campus_model.CampusLandmark, gate_id)
        assert (g.latitude, g.longitude, g.timezone, g.active) == (1.5, 2.5, "Asia/Tokyo", False)
        t = db.get(campus_model.CampusLandmark, terminal_id)
        assert (t.latitude, t.longitude, t.timezone, t.active) == (3.5, 4.5, "Asia/Tokyo", True)
        requests = db.query(campus_model.TravelRequest).all()
        assert {(r.origin_landmark_id, r.hub_id) for r in requests} == {(gate_id, terminal_id)}
    finally:
        db.close()


def test_seed_uses_demo_names_when_an_existing_landmark_has_the_wrong_kind(clock, test_session_factory):
    db = test_session_factory()
    try:
        college = user_model.College(name=demo.DEMO_COLLEGE_NAME)
        db.add(college)
        db.flush()
        # "Main Gate" is a HUB here, "Airport Terminal" a CAMPUS_POINT: both wrong for the demo
        db.add_all([
            campus_model.CampusLandmark(college_id=college.id, name="Main Gate",
                                        kind=campus_model.LandmarkKind.HUB, latitude=9.0, longitude=9.0),
            campus_model.CampusLandmark(college_id=college.id, name="Airport Terminal",
                                        kind=campus_model.LandmarkKind.CAMPUS_POINT, latitude=8.0, longitude=8.0),
        ])
        db.commit()

        demo.seed_demo(db, PASSWORD)
        demo.seed_demo(db, PASSWORD)

        by_name = {l.name: l for l in db.query(campus_model.CampusLandmark).all()}
        assert set(by_name) == {"Main Gate", "Airport Terminal", "Demo Main Gate", "Demo Airport Terminal"}
        assert by_name["Main Gate"].kind == campus_model.LandmarkKind.HUB             # untouched
        assert (by_name["Main Gate"].latitude, by_name["Main Gate"].longitude) == (9.0, 9.0)
        assert by_name["Airport Terminal"].kind == campus_model.LandmarkKind.CAMPUS_POINT
        assert by_name["Demo Main Gate"].kind == campus_model.LandmarkKind.CAMPUS_POINT
        assert by_name["Demo Airport Terminal"].kind == campus_model.LandmarkKind.HUB
        requests = db.query(campus_model.TravelRequest).all()
        assert len(requests) == 2
        assert {(r.origin_landmark_id, r.hub_id) for r in requests} == {
            (by_name["Demo Main Gate"].id, by_name["Demo Airport Terminal"].id)}
    finally:
        db.close()
