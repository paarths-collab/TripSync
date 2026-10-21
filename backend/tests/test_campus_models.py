"""Campus tables: DDL on SQLite + PostgreSQL, DB-level invariants, event helper, views."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core import campus_time
from app.db.database import Base
from app.models import campus_model as m
from app.schemas import campus_schema as schemas
from app.services.campus_events import record_party_event

UTC = timezone.utc
CAMPUS_TABLES = [
    t for t in Base.metadata.sorted_tables
    if t.name in {
        "campus_landmarks", "travel_requests", "pair_suggestions", "corridor_estimates",
        "connection_proposals", "travel_parties", "party_members", "party_events",
        "party_change_proposals", "outbox_messages", "idempotency_records",
    }
]


def test_all_expected_tables_exist():
    assert len(CAMPUS_TABLES) == 11


# --- DDL ---------------------------------------------------------------------
def test_ddl_compiles_for_postgresql_without_native_enums():
    dialect = postgresql.dialect()
    for table in CAMPUS_TABLES:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl
        assert "CREATE TYPE" not in ddl
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=dialect))


def test_enum_columns_are_plain_varchar_32():
    dialect = postgresql.dialect()
    ddl = str(CreateTable(m.TravelRequest.__table__).compile(dialect=dialect))
    assert "direction VARCHAR(32)" in ddl and "status VARCHAR(32)" in ddl
    assert "CREATE TYPE" not in ddl and "ENUM" not in ddl


@pytest.mark.parametrize(
    "table,index_name,expected_where",
    [
        (m.PartyMember.__table__, "uq_active_member_user", "WHERE active"),
        (m.PartyMember.__table__, "uq_active_member_request", "WHERE active"),
        (m.ConnectionProposal.__table__, "uq_pending_proposal_pair", "WHERE state = 'PENDING'"),
        (m.PartyChangeProposal.__table__, "uq_pending_change_party", "WHERE state = 'PENDING'"),
    ],
)
def test_partial_unique_indexes_carry_where_clause(table, index_name, expected_where):
    index = next(i for i in table.indexes if i.name == index_name)
    assert index.unique
    pg = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "CREATE UNIQUE INDEX" in pg and expected_where in pg
    from sqlalchemy.dialects import sqlite
    lite = str(CreateIndex(index).compile(dialect=sqlite.dialect()))
    assert "CREATE UNIQUE INDEX" in lite and "WHERE" in lite


def test_unique_constraints_present_in_postgres_ddl():
    dialect = postgresql.dialect()
    ddl = lambda t: str(CreateTable(t.__table__).compile(dialect=dialect))
    assert "UNIQUE (request_low_id, request_high_id, rule_version)" in ddl(m.PairSuggestion)
    assert "UNIQUE (party_id, version)" in ddl(m.PartyEvent)
    assert "UNIQUE (user_id, operation, key)" in ddl(m.IdempotencyRecord)
    assert "UNIQUE (origin_landmark_id, hub_id, direction)" in ddl(m.CorridorEstimate)
    assert "UNIQUE (college_id, name)" in ddl(m.CampusLandmark)


# --- SQLite invariants -------------------------------------------------------
@pytest.fixture
def world(clock, test_session_factory, college, landmarks, make_user, make_travel_request):
    users = [make_user(f"u{i}@example.test", f"User {i}", college)[0] for i in range(4)]
    reqs = [
        make_travel_request(u, landmarks, start_offset_min=60, end_offset_min=120) for u in users
    ]
    db = test_session_factory()
    yield db, users, reqs, landmarks, clock
    db.rollback()
    db.close()


def _party(db, landmarks, clock):
    party = m.TravelParty(
        agreed_departure=campus_time.to_db(clock.now + timedelta(hours=1)),
        meeting_landmark_id=landmarks["campus"].id,
        hub_id=landmarks["hub"].id,
        direction=m.Direction.TO_HUB,
        timezone="Asia/Kolkata",
        transport_responsibility="text",
    )
    db.add(party)
    db.flush()
    return party


def _member(party, user, req, active=True):
    return m.PartyMember(party_id=party.id, user_id=user.id, request_id=req.id, active=active)


def test_create_all_roundtrip_defaults(world):
    db, users, reqs, lm, clock = world
    party = _party(db, lm, clock)
    db.commit()
    db.refresh(party)
    assert party.state == m.PartyState.AGREED and party.version == 0
    assert party.created_at == campus_time.to_db(clock.now)   # default uses the campus clock


def test_two_active_memberships_for_one_user_conflict(world):
    db, users, reqs, lm, clock = world
    p1, p2 = _party(db, lm, clock), _party(db, lm, clock)
    db.add(_member(p1, users[0], reqs[0]))
    db.commit()
    other_req = reqs[1]
    db.add(_member(p2, users[0], other_req))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_request_in_two_active_parties_conflicts(world):
    db, users, reqs, lm, clock = world
    p1, p2 = _party(db, lm, clock), _party(db, lm, clock)
    db.add(_member(p1, users[0], reqs[0]))
    db.commit()
    db.add(_member(p2, users[1], reqs[0]))
    with pytest.raises(IntegrityError):
        db.commit()


def test_inactive_memberships_do_not_conflict(world):
    db, users, reqs, lm, clock = world
    p1, p2, p3 = (_party(db, lm, clock) for _ in range(3))
    db.add_all([
        _member(p1, users[0], reqs[0], active=False),
        _member(p2, users[0], reqs[0], active=False),   # same user and request, both inactive
        _member(p3, users[0], reqs[0], active=True),     # one active alongside inactive ones
    ])
    db.commit()
    assert db.query(m.PartyMember).count() == 3


def _proposal(users, reqs, state, a=0, b=1, proposer_first=True):
    pu, ru = (users[a], users[b]) if proposer_first else (users[b], users[a])
    pr, rr = (reqs[a], reqs[b]) if proposer_first else (reqs[b], reqs[a])
    return m.ConnectionProposal(
        proposer_id=pu.id, recipient_id=ru.id,
        proposer_request_id=pr.id, recipient_request_id=rr.id,
        proposer_request_version=1, recipient_request_version=1,
        state=state, expires_at=datetime(2026, 3, 1, 6, 0),
    )


def test_pair_columns_are_filled_automatically(world):
    db, users, reqs, lm, clock = world
    p = _proposal(users, reqs, m.ProposalState.PENDING, proposer_first=False)
    db.add(p)
    db.commit()
    assert (p.pair_low_request_id, p.pair_high_request_id) == tuple(sorted((reqs[0].id, reqs[1].id)))


def test_two_pending_proposals_for_same_pair_conflict_even_if_reversed(world):
    db, users, reqs, lm, clock = world
    db.add(_proposal(users, reqs, m.ProposalState.PENDING))
    db.commit()
    db.add(_proposal(users, reqs, m.ProposalState.PENDING, proposer_first=False))
    with pytest.raises(IntegrityError):
        db.commit()


def test_pending_plus_resolved_proposals_for_same_pair_are_fine(world):
    db, users, reqs, lm, clock = world
    db.add_all([
        _proposal(users, reqs, m.ProposalState.DECLINED),
        _proposal(users, reqs, m.ProposalState.EXPIRED),
        _proposal(users, reqs, m.ProposalState.PENDING),
        _proposal(users, reqs, m.ProposalState.WITHDRAWN, proposer_first=False),
    ])
    db.commit()
    assert db.query(m.ConnectionProposal).count() == 4
    # a different pair may also be pending at the same time
    db.add(_proposal(users, reqs, m.ProposalState.PENDING, a=0, b=2))
    db.commit()


def _change(party, user, state):
    return m.PartyChangeProposal(
        party_id=party.id, proposer_id=user.id, note="n", expected_party_version=1, state=state,
    )


def test_two_pending_change_proposals_for_one_party_conflict(world):
    db, users, reqs, lm, clock = world
    party = _party(db, lm, clock)
    db.add(_change(party, users[0], m.ChangeState.PENDING))
    db.commit()
    db.add(_change(party, users[1], m.ChangeState.PENDING))
    with pytest.raises(IntegrityError):
        db.commit()


def test_pending_change_plus_resolved_changes_are_fine(world):
    db, users, reqs, lm, clock = world
    party, other = _party(db, lm, clock), _party(db, lm, clock)
    db.add_all([
        _change(party, users[0], m.ChangeState.REJECTED),
        _change(party, users[0], m.ChangeState.SUPERSEDED),
        _change(party, users[1], m.ChangeState.PENDING),
        _change(other, users[1], m.ChangeState.PENDING),   # another party may have its own
    ])
    db.commit()


def _suggestion(low, high, rule="window-overlap-v1"):
    return m.PairSuggestion(
        request_low_id=low.id, request_high_id=high.id, rule_version=rule,
        reason=m.SuggestionReason.WINDOW_OVERLAP,
        feasible_start=datetime(2026, 3, 1, 5, 0), feasible_end=datetime(2026, 3, 1, 6, 0),
        estimate_status=m.EstimateStatus.UNVERIFIED, estimate_failure="timeout",
        warnings=["deadline_unverified"], valid_until=datetime(2026, 3, 1, 4, 15),
    )


def test_duplicate_pair_suggestion_conflicts_but_new_rule_version_is_fine(world):
    db, users, reqs, lm, clock = world
    low, high = sorted(reqs[:2], key=lambda r: r.id)
    db.add(_suggestion(low, high))
    db.commit()
    db.add(_suggestion(low, high, rule="window-overlap-v2"))
    db.commit()
    db.add(_suggestion(low, high))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    s = db.query(m.PairSuggestion).first()
    assert s.warnings == ["deadline_unverified"]


def test_pair_suggestion_requires_low_below_high(world):
    db, users, reqs, lm, clock = world
    low, high = sorted(reqs[:2], key=lambda r: r.id)
    db.add(_suggestion(high, low))
    with pytest.raises(IntegrityError):
        db.commit()


def test_idempotency_key_is_unique_per_user_and_operation(world):
    db, users, reqs, lm, clock = world

    def rec(user, op="accept_connection", key="k"):
        return m.IdempotencyRecord(
            user_id=user.id, operation=op, key=key, target_id=1,
            response_status=200, response_body={"ok": True},
        )

    db.add_all([rec(users[0]), rec(users[1]), rec(users[0], op="cancel_party")])
    db.commit()
    db.add(rec(users[0]))
    with pytest.raises(IntegrityError):
        db.commit()


def test_landmark_name_unique_per_college(world, college):
    db, users, reqs, lm, clock = world
    db.add(m.CampusLandmark(college_id=college.id, name="Main Gate",
                            kind=m.LandmarkKind.CAMPUS_POINT, latitude=1.0, longitude=2.0))
    with pytest.raises(IntegrityError):
        db.commit()


# --- record_party_event --------------------------------------------------------
def _party_with_members(db, users, reqs, lm, clock):
    party = _party(db, lm, clock)
    db.add_all([_member(party, users[0], reqs[0]), _member(party, users[1], reqs[1])])
    db.flush()
    return party


def test_record_party_event_increments_version_and_creates_outbox_for_both(world):
    db, users, reqs, lm, clock = world
    party = _party_with_members(db, users, reqs, lm, clock)
    now = clock.now
    e1 = record_party_event(db, party, users[0].id, "PARTY_AGREED", {"x": 1}, now)
    e2 = record_party_event(db, party, users[1].id, m.PartyEventType.NOTE_UPDATED, {}, now + timedelta(seconds=5))
    db.commit()

    assert (e1.version, e2.version, party.version) == (1, 2, 2)
    assert e1.event_type == "PARTY_AGREED" and e1.payload == {"x": 1} and e1.actor_id == users[0].id
    assert e2.occurred_at == campus_time.to_db(now + timedelta(seconds=5))

    rows = db.query(m.OutboxMessage).order_by(m.OutboxMessage.id).all()
    assert len(rows) == 4
    assert {(r.event_id, r.recipient_id) for r in rows} == {
        (e1.id, users[0].id), (e1.id, users[1].id), (e2.id, users[0].id), (e2.id, users[1].id)
    }
    first = [r for r in rows if r.event_id == e1.id][0]
    assert first.payload == {"type": "party_event", "party_id": party.id, "version": 1, "event_type": "PARTY_AGREED"}
    assert first.status == m.OutboxStatus.PENDING and first.attempts == 0
    assert first.next_attempt_at == campus_time.to_db(now)


def test_record_party_event_includes_former_members(world):
    db, users, reqs, lm, clock = world
    party = _party_with_members(db, users, reqs, lm, clock)
    for member in party.members:
        member.active = False
    db.flush()
    record_party_event(db, party, users[0].id, "PARTY_CANCELLED", {}, clock.now)
    db.commit()
    assert db.query(m.OutboxMessage).count() == 2


def test_record_party_event_does_not_commit(world):
    db, users, reqs, lm, clock = world
    party = _party_with_members(db, users, reqs, lm, clock)
    db.commit()
    record_party_event(db, party, users[0].id, "PARTY_AGREED", {}, clock.now)

    assert db.query(m.PartyEvent).count() == 1 and db.in_transaction()   # staged only

    db.rollback()
    db.refresh(party)
    assert party.version == 0
    assert db.query(m.PartyEvent).count() == 0 and db.query(m.OutboxMessage).count() == 0


def test_record_party_event_rejects_naive_now_and_unknown_type(world):
    db, users, reqs, lm, clock = world
    party = _party_with_members(db, users, reqs, lm, clock)
    with pytest.raises(ValueError):
        record_party_event(db, party, users[0].id, "PARTY_AGREED", {}, datetime(2026, 3, 1, 4, 0))
    with pytest.raises(ValueError):
        record_party_event(db, party, users[0].id, "NOT_A_TYPE", {}, clock.now)
    assert party.version == 0


def test_event_versions_are_unique_per_party(world):
    db, users, reqs, lm, clock = world
    party = _party_with_members(db, users, reqs, lm, clock)
    record_party_event(db, party, users[0].id, "PARTY_AGREED", {}, clock.now)
    db.commit()
    db.add(m.PartyEvent(party_id=party.id, version=1, event_type="NOTE_UPDATED", payload={}))
    with pytest.raises(IntegrityError):
        db.commit()


# --- schema views ---------------------------------------------------------------
def test_party_view_hides_partner_contact_after_party_ends(world, test_session_factory):
    db, users, reqs, lm, clock = world
    from app.models import profile_model
    db.add(profile_model.Profile(user_id=users[1].id, phone_number="+10000000999"))
    party = _party_with_members(db, users, reqs, lm, clock)
    record_party_event(db, party, users[0].id, "PARTY_AGREED", {}, clock.now)
    db.commit()

    view = schemas.PartyOut.from_party(party, users[0].id)
    assert view.partner.phone_number == "+10000000999" and view.partner.email == users[1].email
    assert [mm.you for mm in view.members] == [True, False]
    assert view.agreed_departure.timezone == "Asia/Kolkata"
    assert view.agreed_departure.utc.endswith("Z")

    party.state = m.PartyState.CANCELLED
    db.commit()
    ended = schemas.PartyOut.from_party(party, users[0].id)
    assert ended.partner.full_name == "User 1"
    assert ended.partner.phone_number is None and ended.partner.email is None


def test_request_view_and_request_body_validation(world):
    db, users, reqs, lm, clock = world
    view = schemas.TravelRequestOut.from_request(reqs[0])
    assert view.earliest_departure.local.endswith("+05:30")
    assert view.status == "OPEN" and view.direction == "TO_HUB"

    base = dict(
        origin_landmark_id=1, hub_id=2, direction="TO_HUB", timezone="Asia/Kolkata",
        earliest_departure="2026-03-01T10:00:00+05:30", latest_departure="2026-03-01T11:00:00+05:30",
    )
    ok = schemas.TravelRequestCreate(**base)
    assert ok.earliest_departure.utcoffset() is not None and ok.flexibility_consent is False
    from pydantic import ValidationError
    for patch in (
        {"earliest_departure": "2026-03-01T10:00:00"},       # naive -> 422
        {"timezone": "Mars/Base"},
        {"direction": "SIDEWAYS"},
    ):
        with pytest.raises(ValidationError):
            schemas.TravelRequestCreate(**{**base, **patch})


def test_openapi_builds_and_legacy_routes_remain():
    from app.main import app
    paths = app.openapi()["paths"]
    assert any(p.startswith("/api/pool") for p in paths)
    assert any(p.startswith("/api/chat") for p in paths)
