"""GET /api/campus/requests/{id}/suggestions and the corridor-estimate adapter."""

import json
import logging
from datetime import timedelta

import pytest

from app.core import campus_rules, campus_time
from app.models import campus_model, user_model
from app.models.campus_model import (
    ConnectionProposal,
    CorridorEstimate,
    PairSuggestion,
    ProposalState,
    TravelRequest,
)
from app.services import campus_estimates, map_service


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------
class FakeProvider:
    """Replaces map_service.get_route_from_ola (no network)."""

    def __init__(self):
        self.calls = 0
        self.mode = "ok"
        self.duration = 1800
        self.distance = 12000

    async def __call__(self, start_lat, start_lng, end_lat, end_lng):
        self.calls += 1
        if self.mode == "ok":
            return {"polyline": [], "distance_meters": self.distance,
                    "duration_seconds": self.duration, "is_fallback": False}
        if self.mode == "none":
            return None
        if self.mode == "timeout":
            raise map_service.RoutingProviderTimeout("Routing provider timed out")
        if self.mode == "error":
            raise map_service.RoutingProviderError("Routing provider unavailable")
        if self.mode == "boom":
            raise ValueError("unexpected")
        if self.mode == "malformed":
            return {"unexpected": True}
        raise AssertionError(self.mode)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", fake)
    return fake


@pytest.fixture
def alice(make_user, college):
    return make_user("alice@example.test", "Alice Example", college, phone="+10000000011")


@pytest.fixture
def bob(make_user, college):
    return make_user("bob@example.test", "Bob Example", college, phone="+10000000012")


@pytest.fixture
def carol(make_user, college):
    return make_user("carol@example.test", "Carol Example", college, phone="+10000000013")


def get_suggestions(client, headers, request_id):
    return client.get(f"/api/campus/requests/{request_id}/suggestions", headers=headers)


def other_ids(resp):
    return [s["other_request"]["id"] for s in resp.json()["suggestions"]]


def edit_request(session_factory, request_id, **fields):
    db = session_factory()
    try:
        db.query(TravelRequest).filter_by(id=request_id).update(fields)
        db.commit()
    finally:
        db.close()


def count(session_factory, model):
    db = session_factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


def snapshot(session_factory):
    db = session_factory()
    try:
        return sorted((r.id, r.status.value, r.version) for r in db.query(TravelRequest).all())
    finally:
        db.close()


# --------------------------------------------------------------------------
# eligibility through the endpoint
# --------------------------------------------------------------------------
def test_future_trips_created_an_hour_apart_suggest_each_other(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=120, end_offset_min=180, created_ago_min=60)
    b = make_travel_request(bob[0], landmarks, start_offset_min=150, end_offset_min=210, created_ago_min=0)

    ra = get_suggestions(client, alice[1], a.id)
    rb = get_suggestions(client, bob[1], b.id)
    assert ra.status_code == rb.status_code == 200
    assert other_ids(ra) == [b.id] and other_ids(rb) == [a.id]
    sa = ra.json()["suggestions"][0]
    assert sa["reason"] == "WINDOW_OVERLAP"
    assert sa["other"] == {"user_id": bob[0].id, "full_name": "Bob Example"}
    assert sa["feasible_window"]["start"]["utc"] == campus_time.utc_iso(clock.at(minutes=150))
    assert sa["feasible_window"]["end"]["utc"] == campus_time.utc_iso(clock.at(minutes=180))
    assert sa["proposal"] is None
    # both sides see the SAME suggestion row
    assert sa["id"] == rb.json()["suggestions"][0]["id"]


def test_same_direction_created_together_but_hours_apart_do_not_match(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=300, end_offset_min=360)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []
    assert get_suggestions(client, bob[1], b.id).json()["suggestions"] == []


def test_opposite_direction_does_not_match(client, clock, provider, alice, bob, landmarks, make_travel_request):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120, direction="FROM_HUB")
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


@pytest.mark.parametrize("field", ["origin_landmark_id", "hub_id"])
def test_different_origin_or_hub_does_not_match(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory, field
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    edit_request(test_session_factory, b.id, **{field: landmarks["campus2"].id})
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


def test_different_college_does_not_match(
    client, clock, provider, alice, landmarks, make_travel_request, make_user, test_session_factory
):
    db = test_session_factory()
    other = user_model.College(name="OTHER")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()

    class _C:
        id = other_id
    stranger = make_user("stranger@example.test", "Stranger", _C)
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    s = make_travel_request(stranger[0], landmarks, start_offset_min=60, end_offset_min=120)
    # same landmarks on purpose: only the college differs
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []
    assert get_suggestions(client, stranger[1], s.id).json()["suggestions"] == []


def test_non_open_candidates_are_not_suggested(
    client, clock, provider, alice, bob, carol, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120, status="RESERVED")
    make_travel_request(carol[0], landmarks, start_offset_min=60, end_offset_min=120, status="CANCELLED")
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


def test_non_open_own_request_gets_no_suggestions_and_no_provider_call(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, status="RESERVED")
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    resp = get_suggestions(client, alice[1], a.id)
    assert resp.status_code == 200 and resp.json()["suggestions"] == []
    assert resp.json()["estimate_status"] == "UNVERIFIED"    # nothing cached yet
    assert provider.calls == 0


def test_own_other_requests_are_never_suggested(client, clock, provider, alice, landmarks, make_travel_request):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


def test_touching_windows_overlap_but_one_second_gap_does_not(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=120, end_offset_min=180)
    resp = get_suggestions(client, alice[1], a.id)
    assert other_ids(resp) == [b.id]
    window = resp.json()["suggestions"][0]["feasible_window"]
    assert window["start"]["utc"] == window["end"]["utc"] == campus_time.utc_iso(clock.at(minutes=120))

    db = test_session_factory()
    row = db.get(TravelRequest, b.id)
    row.earliest_departure = row.earliest_departure + timedelta(seconds=1)
    db.commit()
    db.close()
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


def test_midnight_rollover_in_campus_local_time(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    # clock = 09:30 IST on 2026-03-01; 23:30-00:30 IST is +840..+900 minutes
    a = make_travel_request(alice[0], landmarks, start_offset_min=840, end_offset_min=900)
    b = make_travel_request(bob[0], landmarks, start_offset_min=840, end_offset_min=900)
    resp = get_suggestions(client, alice[1], a.id)
    assert other_ids(resp) == [b.id]
    s = resp.json()["suggestions"][0]
    assert s["feasible_window"]["start"]["local"] == "2026-03-01T23:30:00+05:30"
    assert s["feasible_window"]["end"]["local"] == "2026-03-02T00:30:00+05:30"
    assert s["other_request"]["earliest_departure"]["local"] == "2026-03-01T23:30:00+05:30"
    assert s["other_request"]["latest_departure"]["local"] == "2026-03-02T00:30:00+05:30"
    assert s["feasible_window"]["start"]["timezone"] == "Asia/Kolkata"


def test_mutual_flexibility_bridges_a_small_gap(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, flexibility=True)
    b = make_travel_request(bob[0], landmarks, start_offset_min=170, end_offset_min=230, flexibility=True)
    resp = get_suggestions(client, alice[1], a.id)
    assert other_ids(resp) == [b.id]
    s = resp.json()["suggestions"][0]
    assert s["reason"] == "FLEXIBLE_WINDOW"
    assert s["feasible_window"]["start"]["utc"] == campus_time.utc_iso(clock.at(minutes=140))
    assert s["feasible_window"]["end"]["utc"] == campus_time.utc_iso(clock.at(minutes=150))


def test_one_sided_flexibility_is_not_enough(client, clock, provider, alice, bob, landmarks, make_travel_request):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, flexibility=True)
    b = make_travel_request(bob[0], landmarks, start_offset_min=170, end_offset_min=230, flexibility=False)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []
    assert get_suggestions(client, bob[1], b.id).json()["suggestions"] == []


def test_flexibility_gap_larger_than_two_margins_does_not_match(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, flexibility=True)
    b = make_travel_request(bob[0], landmarks, start_offset_min=181, end_offset_min=240, flexibility=True)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []


def test_multiple_candidates_are_ordered_by_feasible_start(
    client, clock, provider, alice, bob, carol, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=300)
    late = make_travel_request(bob[0], landmarks, start_offset_min=200, end_offset_min=260)
    early = make_travel_request(carol[0], landmarks, start_offset_min=90, end_offset_min=150)
    assert other_ids(get_suggestions(client, alice[1], a.id)) == [early.id, late.id]


# --------------------------------------------------------------------------
# idempotency / no side effects
# --------------------------------------------------------------------------
def test_suggestions_are_idempotent_and_never_change_requests(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=90, end_offset_min=150)
    before = snapshot(test_session_factory)

    first = get_suggestions(client, alice[1], a.id).json()
    second = get_suggestions(client, alice[1], a.id).json()
    from_bob = get_suggestions(client, bob[1], b.id).json()

    assert count(test_session_factory, PairSuggestion) == 1
    assert first["suggestions"][0]["id"] == second["suggestions"][0]["id"] == from_bob["suggestions"][0]["id"]
    assert snapshot(test_session_factory) == before
    # (a suggestion never hides a request from third parties: see
    # test_suggestions_and_proposals_never_hide_a_request_from_third_parties)
    db = test_session_factory()
    row = db.query(PairSuggestion).one()
    assert (row.request_low_id, row.request_high_id) == campus_rules.pair_key(a.id, b.id)
    assert row.rule_version == campus_rules.RULE_VERSION
    db.close()


def test_suggestion_rows_are_refreshed_in_place(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=300)
    b = make_travel_request(bob[0], landmarks, start_offset_min=90, end_offset_min=150)
    first = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]
    assert first["valid_until"]["utc"] == campus_time.utc_iso(
        clock.at(minutes=campus_rules.SUGGESTION_TTL_MINUTES))

    clock.advance(minutes=5)
    edit_request(test_session_factory, b.id, latest_departure=campus_time.to_db(clock.at(minutes=100)),
                 expires_at=campus_time.to_db(clock.at(minutes=100)))
    second = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]
    assert second["id"] == first["id"]
    assert count(test_session_factory, PairSuggestion) == 1
    assert second["valid_until"]["utc"] == campus_time.utc_iso(
        clock.at(minutes=campus_rules.SUGGESTION_TTL_MINUTES))
    assert second["feasible_window"]["end"]["utc"] == campus_time.utc_iso(clock.at(minutes=100))


def test_expired_candidates_are_dropped_lazily(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=300)
    b = make_travel_request(bob[0], landmarks, start_offset_min=10, end_offset_min=60)
    assert other_ids(get_suggestions(client, alice[1], a.id)) == [b.id]
    clock.advance(minutes=61)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"] == []
    db = test_session_factory()
    assert db.get(TravelRequest, b.id).status.value == "EXPIRED"
    assert db.get(TravelRequest, a.id).status.value == "OPEN"
    db.close()


# --------------------------------------------------------------------------
# estimates / provider failures
# --------------------------------------------------------------------------
def test_verified_estimate_is_returned_and_cached(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    first = get_suggestions(client, alice[1], a.id).json()
    second = get_suggestions(client, alice[1], a.id).json()
    assert provider.calls == 1
    assert first["estimate_status"] == "VERIFIED"
    est = first["suggestions"][0]["estimate"]
    assert est["status"] == "VERIFIED" and est["distance_m"] == 12000 and est["duration_s"] == 1800
    assert est["failure"] is None and est["checked_at"]["utc"] == campus_time.utc_iso(clock.now)
    assert second["suggestions"][0]["estimate"] == est
    assert count(test_session_factory, CorridorEstimate) == 1

    # still cached just inside the TTL, refreshed after it
    clock.advance(minutes=campus_rules.ESTIMATE_TTL_MINUTES - 1)
    edit_request(test_session_factory, a.id, latest_departure=campus_time.to_db(clock.at(minutes=60)),
                 expires_at=campus_time.to_db(clock.at(minutes=60)))
    get_suggestions(client, alice[1], a.id)
    assert provider.calls == 1
    clock.advance(minutes=2)
    get_suggestions(client, alice[1], a.id)
    assert provider.calls == 2


def test_estimates_are_cached_per_direction(client, clock, provider, alice, landmarks, make_travel_request):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(alice[0], landmarks, start_offset_min=200, end_offset_min=260, direction="FROM_HUB")
    get_suggestions(client, alice[1], a.id)
    get_suggestions(client, alice[1], b.id)
    assert provider.calls == 2


def test_direction_decides_route_endpoints(monkeypatch, clock, landmarks, test_session_factory):
    seen = []

    async def fake(slat, slng, elat, elng):
        seen.append(((slat, slng), (elat, elng)))
        return {"distance_meters": 1, "duration_seconds": 2}

    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", fake)
    import asyncio
    db = test_session_factory()
    try:
        campus = db.get(campus_model.CampusLandmark, landmarks["campus"].id)
        hub = db.get(campus_model.CampusLandmark, landmarks["hub"].id)
        asyncio.run(campus_estimates.corridor_estimate(db, campus, hub, "TO_HUB", clock.now))
        asyncio.run(campus_estimates.corridor_estimate(db, campus, hub, "FROM_HUB", clock.now))
        db.commit()
    finally:
        db.close()
    assert seen[0] == ((19.1000, 72.8400), (19.0900, 72.8700))
    assert seen[1] == ((19.0900, 72.8700), (19.1000, 72.8400))


@pytest.mark.parametrize("mode,failure", [
    ("timeout", "timeout"),
    ("error", "unavailable"),
    ("boom", "unavailable"),
    ("malformed", "unavailable"),
    ("none", "no_route"),
])
def test_provider_failure_still_returns_suggestions_unverified(
    client, clock, provider, alice, bob, landmarks, make_travel_request, mode, failure
):
    provider.mode = mode
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    resp = get_suggestions(client, alice[1], a.id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estimate_status"] == "UNVERIFIED"
    assert [s["other_request"]["id"] for s in data["suggestions"]] == [b.id]    # never an empty list
    est = data["suggestions"][0]["estimate"]
    assert est["status"] == "UNVERIFIED" and est["failure"] == failure
    assert est["distance_m"] is None and est["duration_s"] is None


def test_unverified_estimate_is_not_retried_before_the_retry_window_then_recovers(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.mode = "timeout"
    a = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=300)
    make_travel_request(bob[0], landmarks, start_offset_min=10, end_offset_min=300)

    assert get_suggestions(client, alice[1], a.id).json()["estimate_status"] == "UNVERIFIED"
    assert provider.calls == 1
    provider.mode = "ok"                     # provider recovers, but we must not hammer it
    clock.advance(seconds=campus_rules.ESTIMATE_RETRY_SECONDS - 1)
    still = get_suggestions(client, alice[1], a.id).json()
    assert provider.calls == 1
    assert still["estimate_status"] == "UNVERIFIED"
    assert len(still["suggestions"]) == 1

    clock.advance(seconds=2)
    recovered = get_suggestions(client, alice[1], a.id).json()
    assert provider.calls == 2
    assert recovered["estimate_status"] == "VERIFIED"
    sug = recovered["suggestions"][0]
    assert sug["estimate"]["status"] == "VERIFIED" and sug["estimate"]["failure"] is None
    assert sug["estimate"]["duration_s"] == 1800


def test_verified_estimate_that_fails_on_refresh_degrades_to_unverified(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=900)
    make_travel_request(bob[0], landmarks, start_offset_min=10, end_offset_min=900)
    assert get_suggestions(client, alice[1], a.id).json()["estimate_status"] == "VERIFIED"
    clock.advance(minutes=campus_rules.ESTIMATE_TTL_MINUTES + 1)
    provider.mode = "error"
    data = get_suggestions(client, alice[1], a.id).json()
    assert data["estimate_status"] == "UNVERIFIED" and len(data["suggestions"]) == 1
    assert count(test_session_factory, CorridorEstimate) == 1


def test_adapter_never_raises_even_if_cache_write_fails(monkeypatch, clock, landmarks, test_session_factory):
    import asyncio
    provider = FakeProvider()
    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", provider)
    db = test_session_factory()
    try:
        campus = db.get(campus_model.CampusLandmark, landmarks["campus"].id)
        hub = db.get(campus_model.CampusLandmark, landmarks["hub"].id)

        def explode(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(db, "begin_nested", explode)
        row = asyncio.run(campus_estimates.corridor_estimate(db, campus, hub, "TO_HUB", clock.now))
        assert row.status == campus_model.EstimateStatus.VERIFIED       # still answered
        assert row.duration_s == 1800
    finally:
        db.close()


def test_adapter_has_its_own_call_deadline(monkeypatch, clock, landmarks, test_session_factory):
    import asyncio

    async def hang(*a, **k):
        await asyncio.sleep(30)

    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", hang)
    monkeypatch.setattr(campus_estimates, "PROVIDER_CALL_TIMEOUT_SECONDS", 0.05)
    db = test_session_factory()
    try:
        campus = db.get(campus_model.CampusLandmark, landmarks["campus"].id)
        hub = db.get(campus_model.CampusLandmark, landmarks["hub"].id)
        row = asyncio.run(campus_estimates.corridor_estimate(db, campus, hub, "TO_HUB", clock.now))
        assert row.status == campus_model.EstimateStatus.UNVERIFIED and row.failure == "timeout"
    finally:
        db.close()


def test_provider_failure_logs_no_coordinates_or_keys(
    client, clock, provider, alice, bob, landmarks, make_travel_request, caplog
):
    provider.mode = "error"
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    with caplog.at_level(logging.INFO):
        get_suggestions(client, alice[1], a.id)
    text = caplog.text
    for secret in ("19.1", "19.09", "72.84", "72.87", "test-ola-key", "api_key", "olamaps"):
        assert secret not in text


# --------------------------------------------------------------------------
# deadlines
# --------------------------------------------------------------------------
def test_verified_estimate_that_cannot_meet_arrive_by_warns(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.duration = 3000       # 50 minutes
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=240, arrive_by=100)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=240)
    s = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]
    assert s["warnings"] == ["cannot_meet_arrive_by"]     # leaves at +60, arrives +110 > +100


def test_deadline_is_judged_from_the_earliest_departure_not_window_end(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.duration = 1800       # 30 minutes: fine when leaving at +60 even though the window ends at +240
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=240, arrive_by=100)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=240)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["warnings"] == []


def test_deadline_uses_now_when_the_window_already_started(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.duration = 1800
    a = make_travel_request(alice[0], landmarks, start_offset_min=-30, end_offset_min=240, arrive_by=45)
    make_travel_request(bob[0], landmarks, start_offset_min=-30, end_offset_min=240)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["warnings"] == []
    clock.advance(minutes=20)       # leaving "now" (+20) + 30 min = +50 > +45
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["warnings"] == ["cannot_meet_arrive_by"]


def test_either_partys_deadline_counts(client, clock, provider, alice, bob, landmarks, make_travel_request):
    provider.duration = 3000
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=240)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=240, arrive_by=100)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["warnings"] == ["cannot_meet_arrive_by"]


def test_unverified_estimate_with_deadline_warns_deadline_unverified(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.mode = "error"
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=240, arrive_by=100)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=240)
    s = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]
    assert s["warnings"] == ["deadline_unverified"]


def test_no_deadline_means_no_warnings_even_when_unverified(
    client, clock, provider, alice, bob, landmarks, make_travel_request
):
    provider.mode = "timeout"
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=240)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=240)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["warnings"] == []


# --------------------------------------------------------------------------
# privacy / access
# --------------------------------------------------------------------------
def test_suggestions_never_expose_contact_details(
    client, clock, provider, alice, bob, carol, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(carol[0], landmarks, start_offset_min=60, end_offset_min=120)
    resp = get_suggestions(client, alice[1], a.id)
    assert len(resp.json()["suggestions"]) == 2
    text = json.dumps(resp.json()).lower()
    for forbidden in ("phone", "email", "@example.test", "+10000000012", "+10000000013",
                      "bob@", "carol@", "hashed_password", "password"):
        assert forbidden not in text
    for s in resp.json()["suggestions"]:
        assert set(s["other"]) == {"user_id", "full_name"}
        assert set(s["other_request"]) == {"id", "earliest_departure", "latest_departure"}
        assert "user_id" not in s["other_request"] and "arrive_by" not in s["other_request"]


def test_unrelated_user_cannot_read_someone_elses_requests_or_suggestions(
    client, clock, provider, alice, bob, carol, landmarks, make_travel_request
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    # carol has no request of her own; she is "a third user"
    assert get_suggestions(client, carol[1], a.id).status_code == 404
    assert get_suggestions(client, carol[1], b.id).status_code == 404
    assert client.get(f"/api/campus/requests/{a.id}", headers=carol[1]).status_code == 404
    assert client.get("/api/campus/requests", headers=carol[1]).json() == []
    # even a counterpart (bob) cannot read alice's suggestions: owner only
    assert get_suggestions(client, bob[1], a.id).status_code == 404
    assert get_suggestions(client, alice[1], 99999).status_code == 404


def test_suggestions_require_authentication(client):
    assert client.get("/api/campus/requests/1/suggestions").status_code == 401


# --------------------------------------------------------------------------
# proposal info
# --------------------------------------------------------------------------
def _proposal(session_factory, clock, proposer, recipient, req_p, req_r, state=ProposalState.PENDING, party_id=None):
    db = session_factory()
    try:
        row = ConnectionProposal(
            proposer_id=proposer.id, recipient_id=recipient.id,
            proposer_request_id=req_p.id, recipient_request_id=req_r.id,
            proposer_request_version=1, recipient_request_version=1,
            state=state, expires_at=campus_time.to_db(clock.at(minutes=30)), party_id=party_id,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_pending_proposal_is_reported_per_viewer(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    pid = _proposal(test_session_factory, clock, bob[0], alice[0], b, a)
    mine = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]
    theirs = get_suggestions(client, bob[1], b.id).json()["suggestions"][0]
    assert mine["proposal"] == {"id": pid, "state": "PENDING", "direction": "incoming"}
    assert theirs["proposal"] == {"id": pid, "state": "PENDING", "direction": "outgoing"}


def test_resolved_proposals_are_not_reported(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    _proposal(test_session_factory, clock, bob[0], alice[0], b, a, state=ProposalState.DECLINED)
    _proposal(test_session_factory, clock, bob[0], alice[0], b, a, state=ProposalState.EXPIRED)
    assert get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["proposal"] is None


def test_accepted_proposal_with_active_party_is_reported(
    client, clock, provider, alice, bob, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    db = test_session_factory()
    party = campus_model.TravelParty(
        state=campus_model.PartyState.AGREED, agreed_departure=campus_time.to_db(clock.at(minutes=60)),
        meeting_landmark_id=landmarks["campus"].id, hub_id=landmarks["hub"].id,
        direction=campus_model.Direction.TO_HUB, timezone="Asia/Kolkata",
        transport_responsibility=campus_rules.TRANSPORT_RESPONSIBILITY_TEXT,
    )
    db.add(party)
    db.commit()
    party_id = party.id
    db.close()
    pid = _proposal(test_session_factory, clock, bob[0], alice[0], b, a,
                    state=ProposalState.ACCEPTED, party_id=party_id)
    got = get_suggestions(client, alice[1], a.id).json()["suggestions"][0]["proposal"]
    assert got == {"id": pid, "state": "ACCEPTED", "direction": "incoming"}


# --------------------------------------------------------------------------
# write ordering / no needless updates (deadlock avoidance)
# --------------------------------------------------------------------------
class StatementLog:
    """Records INSERT/UPDATE statements on pair_suggestions in execution order."""

    def __init__(self, engine):
        from sqlalchemy import event
        self.engine = engine
        self.writes = []
        self._event = event
        event.listen(engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        if not head.startswith(("INSERT INTO PAIR_SUGGESTIONS", "UPDATE PAIR_SUGGESTIONS")):
            return
        if head.startswith("INSERT"):
            import re
            cols = [c.strip() for c in re.search(r"\(([^)]*)\)", statement).group(1).split(",")]
            params = list(parameters)
            self.writes.append(("INSERT", params[cols.index("request_low_id")], params[cols.index("request_high_id")]))
        elif head.startswith("UPDATE"):
            self.writes.append(("UPDATE", None, None))

    def clear(self):
        self.writes.clear()

    def close(self):
        self._event.remove(self.engine, "before_cursor_execute", self._on)


@pytest.fixture
def stmt_log(test_engine):
    log = StatementLog(test_engine)
    yield log
    log.close()


def test_suggestion_rows_are_written_in_ascending_pair_order(
    client, clock, provider, alice, bob, carol, landmarks, make_user, college,
    make_travel_request, stmt_log
):
    dave = make_user("dave@example.test", "Dave Example", college)
    erin = make_user("erin@example.test", "Erin Example", college)
    # candidate ids 1..3 get midpoints such that closeness order (3, 1, 2) differs from id order
    c1 = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=100)     # mid 80
    c2 = make_travel_request(carol[0], landmarks, start_offset_min=60, end_offset_min=80)    # mid 70
    c3 = make_travel_request(dave[0], landmarks, start_offset_min=80, end_offset_min=120)    # mid 100
    me = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=140)   # mid 100
    stmt_log.clear()

    resp = get_suggestions(client, alice[1], me.id)
    assert len(resp.json()["suggestions"]) == 3
    inserts = [(low, high) for kind, low, high in stmt_log.writes if kind == "INSERT"]
    assert inserts == sorted(inserts) and len(inserts) == 3
    assert inserts == [(c1.id, me.id), (c2.id, me.id), (c3.id, me.id)]


def test_second_get_performs_no_update_of_unchanged_rows(
    client, clock, provider, alice, bob, landmarks, make_travel_request, stmt_log
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=90, end_offset_min=150)
    get_suggestions(client, alice[1], a.id)
    stmt_log.clear()

    get_suggestions(client, alice[1], a.id)
    clock.advance(seconds=30)            # within the valid_until refresh slack
    get_suggestions(client, alice[1], a.id)
    assert [w for w in stmt_log.writes if w[0] in ("INSERT", "UPDATE")] == []

    clock.advance(minutes=5)             # now the TTL refresh is due: exactly one UPDATE
    get_suggestions(client, alice[1], a.id)
    assert [w[0] for w in stmt_log.writes] == ["UPDATE"]


# --------------------------------------------------------------------------
# candidate cap fairness
# --------------------------------------------------------------------------
def test_candidate_cap_keeps_the_closest_windows_and_flags_truncation(
    client, clock, provider, alice, landmarks, make_user, college, make_travel_request, monkeypatch
):
    from app.services import campus_suggestion_service
    monkeypatch.setattr(campus_suggestion_service, "MAX_CANDIDATES", 3)
    me = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=300)   # mid 180
    windows = {"c1": (60, 100), "c2": (70, 110), "c3": (80, 120),        # mids 80, 90, 100 (far)
               "c4": (170, 190), "c5": (160, 200), "c6": (200, 240)}      # mids 180, 180, 220 (close)
    ids = {}
    for name, (start, end) in windows.items():
        user = make_user(f"{name}@example.test", name.upper(), college)[0]
        ids[name] = make_travel_request(user, landmarks, start_offset_min=start, end_offset_min=end).id

    data = get_suggestions(client, alice[1], me.id).json()
    assert data["truncated"] is True
    assert sorted(other_ids_from(data)) == sorted([ids["c4"], ids["c5"], ids["c6"]])

    monkeypatch.setattr(campus_suggestion_service, "MAX_CANDIDATES", 6)
    data = get_suggestions(client, alice[1], me.id).json()
    assert data["truncated"] is False and len(data["suggestions"]) == 6


def other_ids_from(data):
    return [s["other_request"]["id"] for s in data["suggestions"]]


def test_truncated_is_false_for_a_normal_search(client, clock, provider, alice, bob, landmarks, make_travel_request):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    assert get_suggestions(client, alice[1], a.id).json()["truncated"] is False


# --------------------------------------------------------------------------
# provider await must not hold a DB transaction
# --------------------------------------------------------------------------
def test_adapter_releases_the_transaction_before_calling_the_provider(
    monkeypatch, clock, landmarks, test_session_factory
):
    import asyncio
    db = test_session_factory()
    seen = {}

    async def fake(slat, slng, elat, elng):
        seen["in_transaction"] = db.in_transaction()
        return {"distance_meters": 5, "duration_seconds": 6}

    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", fake)
    try:
        campus = db.get(campus_model.CampusLandmark, landmarks["campus"].id)
        hub = db.get(campus_model.CampusLandmark, landmarks["hub"].id)
        row = asyncio.run(campus_estimates.corridor_estimate(
            db, campus, hub, "TO_HUB", clock.now, release_transaction=True))
        assert seen["in_transaction"] is False
        assert row.status == campus_model.EstimateStatus.VERIFIED and row.duration_s == 6
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# a suggestion / proposal never hides a request from other searchers
# --------------------------------------------------------------------------
def test_suggestions_and_proposals_never_hide_a_request_from_third_parties(
    client, clock, provider, alice, bob, carol, landmarks, make_travel_request, test_session_factory
):
    a = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    b = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    c = make_travel_request(carol[0], landmarks, start_offset_min=60, end_offset_min=120)
    # alice and bob already have a suggestion between them and a PENDING proposal
    get_suggestions(client, alice[1], a.id)
    pid = _proposal(test_session_factory, clock, bob[0], alice[0], b, a)

    seen = get_suggestions(client, carol[1], c.id).json()["suggestions"]
    assert sorted(s["other_request"]["id"] for s in seen) == sorted([a.id, b.id])
    assert all(s["proposal"] is None for s in seen)          # the A-B proposal is not carol's pair
    # alice and bob still see each other and carol
    assert sorted(other_ids(get_suggestions(client, alice[1], a.id))) == sorted([b.id, c.id])
    by_other = {s["other_request"]["id"]: s for s in get_suggestions(client, alice[1], a.id).json()["suggestions"]}
    assert by_other[b.id]["proposal"]["id"] == pid
    assert snapshot(test_session_factory) == [(a.id, "OPEN", 1), (b.id, "OPEN", 1), (c.id, "OPEN", 1)]
