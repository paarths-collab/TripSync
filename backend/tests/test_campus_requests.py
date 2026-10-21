"""Campus landmarks + travel-request CRUD (/api/campus/landmarks, /api/campus/requests)."""

from datetime import timedelta

import pytest

from app.core import campus_rules, campus_time
from app.models import campus_model, user_model
from app.models.campus_model import (
    ConnectionProposal,
    PairSuggestion,
    ProposalState,
    TravelRequest,
    TravelRequestStatus,
)
from app.services import campus_request_service


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
@pytest.fixture
def alice(make_user, college):
    return make_user("alice@example.test", "Alice Example", college, phone="+10000000011")


@pytest.fixture
def bob(make_user, college):
    return make_user("bob@example.test", "Bob Example", college, phone="+10000000012")


def iso(dt):
    return dt.isoformat()


def body(clock, landmarks, start, end, **kw):
    """Request body with a window [now+start, now+end] minutes."""
    data = {
        "origin_landmark_id": landmarks["campus"].id,
        "hub_id": landmarks["hub"].id,
        "direction": "TO_HUB",
        "earliest_departure": iso(clock.at(minutes=start)),
        "latest_departure": iso(clock.at(minutes=end)),
        "timezone": "Asia/Kolkata",
    }
    data.update(kw)
    return data


def create(client, headers, payload):
    return client.post("/api/campus/requests", json=payload, headers=headers)


def error_code(resp):
    detail = resp.json()["detail"]
    return detail["code"] if isinstance(detail, dict) else detail


def seed_suggestion(session_factory, low_id, high_id, clock):
    db = session_factory()
    try:
        now = campus_time.to_db(clock.now)
        row = PairSuggestion(
            request_low_id=low_id, request_high_id=high_id,
            rule_version=campus_rules.RULE_VERSION,
            reason=campus_model.SuggestionReason.WINDOW_OVERLAP,
            feasible_start=now, feasible_end=now,
            estimate_status=campus_model.EstimateStatus.UNVERIFIED,
            warnings=[], valid_until=now,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def seed_proposal(session_factory, clock, proposer, recipient, req_p, req_r,
                  suggestion_id=None, state=ProposalState.PENDING, minutes=30):
    db = session_factory()
    try:
        row = ConnectionProposal(
            suggestion_id=suggestion_id,
            proposer_id=proposer.id, recipient_id=recipient.id,
            proposer_request_id=req_p.id, recipient_request_id=req_r.id,
            proposer_request_version=req_p.version, recipient_request_version=req_r.version,
            state=state,
            expires_at=campus_time.to_db(clock.at(minutes=minutes)),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def reload(session_factory, model, row_id):
    db = session_factory()
    try:
        row = db.get(model, row_id)
        db.expunge(row)
        return row
    finally:
        db.close()


# --------------------------------------------------------------------------
# landmarks
# --------------------------------------------------------------------------
def test_landmarks_are_scoped_to_callers_college(client, alice, landmarks, test_session_factory, make_user):
    resp = client.get("/api/campus/landmarks", headers=alice[1])
    assert resp.status_code == 200
    names = {l["name"]: l for l in resp.json()}
    assert set(names) == {"Main Gate", "Airport Terminal", "Library"}
    assert names["Main Gate"]["kind"] == "CAMPUS_POINT"
    assert names["Airport Terminal"]["kind"] == "HUB"
    assert set(names["Main Gate"]) == {"id", "name", "kind", "latitude", "longitude", "timezone"}

    db = test_session_factory()
    other = user_model.College(name="OTHER")
    db.add(other)
    db.commit()
    oid = other.id
    db.close()

    class _C:
        id = oid
    outsider = make_user("out@example.test", "Out Sider", _C)
    assert client.get("/api/campus/landmarks", headers=outsider[1]).json() == []


def test_landmarks_hide_inactive_ones(client, alice, landmarks, test_session_factory):
    db = test_session_factory()
    db.query(campus_model.CampusLandmark).filter_by(id=landmarks["campus2"].id).update({"active": False})
    db.commit()
    db.close()
    names = {l["name"] for l in client.get("/api/campus/landmarks", headers=alice[1]).json()}
    assert "Library" not in names


def test_endpoints_require_authentication(client):
    assert client.get("/api/campus/landmarks").status_code == 401
    assert client.get("/api/campus/requests").status_code == 401
    assert client.post("/api/campus/requests", json={}).status_code == 401


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------
def test_create_request_returns_201_with_local_times(client, clock, alice, landmarks):
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, arrive_by=iso(clock.at(minutes=240))))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "OPEN" and data["version"] == 1
    assert data["user_id"] == alice[0].id and data["college_id"] == alice[0].college_id
    assert data["mode"] == "SHARED_TAXI_PARTY" and data["direction"] == "TO_HUB"
    assert data["earliest_departure"]["utc"] == "2026-03-01T05:00:00Z"
    assert data["earliest_departure"]["local"] == "2026-03-01T10:30:00+05:30"
    assert data["earliest_departure"]["timezone"] == "Asia/Kolkata"
    assert data["arrive_by"]["utc"] == "2026-03-01T08:00:00Z"
    assert data["flexibility_consent"] is False
    # expires_at defaults to latest_departure
    assert data["expires_at"]["utc"] == data["latest_departure"]["utc"]


def test_create_accepts_other_offsets_and_normalises_to_utc(client, clock, alice, landmarks):
    payload = body(clock, landmarks, 60, 120)
    payload["earliest_departure"] = "2026-03-01T10:30:00+05:30"   # == 05:00Z == now+60m
    payload["latest_departure"] = "2026-03-01T11:30:00+05:30"
    resp = create(client, alice[1], payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["earliest_departure"]["utc"] == "2026-03-01T05:00:00Z"


def test_expires_at_is_clamped_to_one_hour_after_latest(client, clock, alice, landmarks):
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, expires_at=iso(clock.at(hours=10))))
    assert resp.status_code == 201
    assert resp.json()["expires_at"]["utc"] == campus_time.utc_iso(clock.at(minutes=180))
    resp = create(client, alice[1], body(clock, landmarks, 300, 330, expires_at=iso(clock.at(minutes=310))))
    assert resp.json()["expires_at"]["utc"] == campus_time.utc_iso(clock.at(minutes=310))


def test_expires_at_in_the_past_is_rejected(client, clock, alice, landmarks):
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, expires_at=iso(clock.at(minutes=-5))))
    assert resp.status_code == 422
    assert error_code(resp) == "invalid_expires_at"


def test_naive_datetime_is_rejected_with_422(client, clock, alice, landmarks):
    payload = body(clock, landmarks, 60, 120)
    payload["earliest_departure"] = "2026-03-01T10:30:00"
    assert create(client, alice[1], payload).status_code == 422
    payload = body(clock, landmarks, 60, 120, arrive_by="2026-03-01T12:30:00")
    assert create(client, alice[1], payload).status_code == 422


@pytest.mark.parametrize("start,end,code", [
    (60, 65, campus_rules.ERR_TOO_SHORT),
    (60, 60 + 6 * 60 + 1, campus_rules.ERR_TOO_LONG),
    (-120, -60, campus_rules.ERR_ALREADY_ENDED),
    (120, 60, campus_rules.ERR_ORDER),
    (15 * 24 * 60, 15 * 24 * 60 + 60, campus_rules.ERR_TOO_FAR),
])
def test_invalid_windows_are_422(client, clock, alice, landmarks, start, end, code):
    resp = create(client, alice[1], body(clock, landmarks, start, end))
    assert resp.status_code == 422
    assert error_code(resp) == code


def test_window_length_boundaries_are_accepted(client, clock, alice, landmarks):
    assert create(client, alice[1], body(clock, landmarks, 60, 70)).status_code == 201          # exactly 10 min
    assert create(client, alice[1], body(clock, landmarks, 100, 100 + 360)).status_code == 201  # exactly 6 h


def test_invalid_timezone_and_direction_are_422(client, clock, alice, landmarks):
    assert create(client, alice[1], body(clock, landmarks, 60, 120, timezone="Mars/Olympus")).status_code == 422
    assert create(client, alice[1], body(clock, landmarks, 60, 120, direction="SIDEWAYS")).status_code == 422
    assert create(client, alice[1], body(clock, landmarks, 60, 120, surprise=1)).status_code == 422


def test_arrive_by_must_be_after_window_start(client, clock, alice, landmarks):
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, arrive_by=iso(clock.at(minutes=30))))
    assert resp.status_code == 422
    assert error_code(resp) == "arrive_by_before_window"


def test_landmark_of_another_college_is_rejected(client, clock, alice, landmarks, test_session_factory):
    db = test_session_factory()
    other = user_model.College(name="OTHER")
    db.add(other)
    db.commit()
    foreign = campus_model.CampusLandmark(
        college_id=other.id, name="Far Gate", kind=campus_model.LandmarkKind.CAMPUS_POINT,
        latitude=1.0, longitude=2.0, timezone="Asia/Kolkata", active=True,
    )
    db.add(foreign)
    db.commit()
    foreign_id = foreign.id
    db.close()
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, origin_landmark_id=foreign_id))
    assert resp.status_code == 422
    assert error_code(resp) == "invalid_origin_landmark"
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, origin_landmark_id=99999))
    assert resp.status_code == 422


def test_wrong_landmark_kind_is_rejected(client, clock, alice, landmarks):
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, origin_landmark_id=landmarks["hub"].id))
    assert resp.status_code == 422 and error_code(resp) == "invalid_origin_landmark"
    resp = create(client, alice[1], body(clock, landmarks, 60, 120, hub_id=landmarks["campus2"].id))
    assert resp.status_code == 422 and error_code(resp) == "invalid_hub_landmark"


def test_inactive_landmark_is_rejected(client, clock, alice, landmarks, test_session_factory):
    db = test_session_factory()
    db.query(campus_model.CampusLandmark).filter_by(id=landmarks["hub"].id).update({"active": False})
    db.commit()
    db.close()
    resp = create(client, alice[1], body(clock, landmarks, 60, 120))
    assert resp.status_code == 422 and error_code(resp) == "invalid_hub_landmark"


def test_overlapping_request_on_same_corridor_is_409(client, clock, alice, landmarks):
    first = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    resp = create(client, alice[1], body(clock, landmarks, 100, 160))
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "overlapping_request"
    assert detail["current"]["request"]["id"] == first["id"]
    # touching windows overlap too
    assert error_code(create(client, alice[1], body(clock, landmarks, 120, 180))) == "overlapping_request"
    # a gap is fine
    assert create(client, alice[1], body(clock, landmarks, 121, 180)).status_code == 201


def test_overlap_rule_ignores_other_direction_corridor_and_users(client, clock, alice, bob, landmarks):
    assert create(client, alice[1], body(clock, landmarks, 60, 120)).status_code == 201
    assert create(client, alice[1], body(clock, landmarks, 60, 120, direction="FROM_HUB")).status_code == 201
    assert create(
        client, alice[1], body(clock, landmarks, 60, 120, origin_landmark_id=landmarks["campus2"].id)
    ).status_code == 201
    assert create(client, bob[1], body(clock, landmarks, 60, 120)).status_code == 201


def test_cancelled_request_no_longer_blocks_overlap(client, clock, alice, landmarks):
    first = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    assert client.delete(f"/api/campus/requests/{first['id']}", headers=alice[1]).status_code == 200
    assert create(client, alice[1], body(clock, landmarks, 60, 120)).status_code == 201


def test_max_open_requests_per_user(client, clock, alice, bob, landmarks):
    for start in (60, 200, 340):
        assert create(client, alice[1], body(clock, landmarks, start, start + 60)).status_code == 201
    assert campus_rules.MAX_OPEN_REQUESTS_PER_USER == 3
    resp = create(client, alice[1], body(clock, landmarks, 480, 540))
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "max_open_requests"
    # other users are unaffected; cancelling frees a slot
    assert create(client, bob[1], body(clock, landmarks, 480, 540)).status_code == 201
    first_id = client.get("/api/campus/requests", headers=alice[1]).json()[-1]["id"]
    client.delete(f"/api/campus/requests/{first_id}", headers=alice[1])
    assert create(client, alice[1], body(clock, landmarks, 480, 540)).status_code == 201


def test_creating_a_request_does_not_depend_on_other_users(client, clock, alice, bob, landmarks, make_travel_request):
    other = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    resp = create(client, alice[1], body(clock, landmarks, 60, 120))
    assert resp.status_code == 201
    assert "suggestions" not in resp.json()
    assert reload_status(client, bob[1], other.id) == "OPEN"


def reload_status(client, headers, request_id):
    return client.get(f"/api/campus/requests/{request_id}", headers=headers).json()["status"]


# --------------------------------------------------------------------------
# read / list / owner-only
# --------------------------------------------------------------------------
def test_list_and_filter_my_requests(client, clock, alice, bob, landmarks):
    a1 = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    a2 = create(client, alice[1], body(clock, landmarks, 200, 260)).json()
    create(client, bob[1], body(clock, landmarks, 60, 120))
    client.delete(f"/api/campus/requests/{a1['id']}", headers=alice[1])

    mine = client.get("/api/campus/requests", headers=alice[1]).json()
    assert {r["id"] for r in mine} == {a1["id"], a2["id"]}
    open_only = client.get("/api/campus/requests?status=OPEN", headers=alice[1]).json()
    assert [r["id"] for r in open_only] == [a2["id"]]
    cancelled = client.get("/api/campus/requests?status=CANCELLED", headers=alice[1]).json()
    assert [r["id"] for r in cancelled] == [a1["id"]]
    assert client.get("/api/campus/requests?status=BOGUS", headers=alice[1]).status_code == 422


def test_requests_are_owner_only_with_404(client, clock, alice, bob, landmarks):
    mine = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    url = f"/api/campus/requests/{mine['id']}"
    assert client.get(url, headers=alice[1]).status_code == 200
    assert client.get(url, headers=bob[1]).status_code == 404
    assert client.patch(url, json={"expected_version": 1, "flexibility_consent": True}, headers=bob[1]).status_code == 404
    assert client.delete(url, headers=bob[1]).status_code == 404
    assert client.get(url + "/suggestions", headers=bob[1]).status_code == 404
    assert client.get("/api/campus/requests/99999", headers=alice[1]).status_code == 404
    # nothing changed
    assert client.get(url, headers=alice[1]).json()["version"] == 1


# --------------------------------------------------------------------------
# PATCH
# --------------------------------------------------------------------------
def test_patch_bumps_version_and_updates_fields(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    resp = client.patch(
        f"/api/campus/requests/{req['id']}",
        json={"expected_version": 1, "latest_departure": iso(clock.at(minutes=150)),
              "flexibility_consent": True, "arrive_by": iso(clock.at(minutes=300))},
        headers=alice[1],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["version"] == 2
    assert data["flexibility_consent"] is True
    assert data["latest_departure"]["utc"] == campus_time.utc_iso(clock.at(minutes=150))
    assert data["expires_at"]["utc"] == data["latest_departure"]["utc"]   # follows the new end
    assert data["arrive_by"] is not None

    # explicit null clears arrive_by; omitted leaves it
    resp = client.patch(
        f"/api/campus/requests/{req['id']}",
        json={"expected_version": 2, "arrive_by": None}, headers=alice[1],
    )
    assert resp.json()["arrive_by"] is None and resp.json()["version"] == 3
    resp = client.patch(
        f"/api/campus/requests/{req['id']}",
        json={"expected_version": 3, "flexibility_consent": False}, headers=alice[1],
    )
    assert resp.json()["flexibility_consent"] is False


def test_patch_stale_version_is_409_with_current_request(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    url = f"/api/campus/requests/{req['id']}"
    ok = client.patch(url, json={"expected_version": 1, "flexibility_consent": True}, headers=alice[1])
    assert ok.status_code == 200
    stale = client.patch(url, json={"expected_version": 1, "flexibility_consent": False}, headers=alice[1])
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["code"] == "stale_version"
    assert detail["current"]["request"]["version"] == 2
    assert detail["current"]["request"]["flexibility_consent"] is True


def test_patch_validates_the_new_window(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    url = f"/api/campus/requests/{req['id']}"
    resp = client.patch(url, json={"expected_version": 1, "latest_departure": iso(clock.at(minutes=60 + 7 * 60))},
                        headers=alice[1])
    assert resp.status_code == 422 and error_code(resp) == campus_rules.ERR_TOO_LONG
    resp = client.patch(url, json={"expected_version": 1, "earliest_departure": "2026-03-01T10:30:00"},
                        headers=alice[1])
    assert resp.status_code == 422
    assert client.get(url, headers=alice[1]).json()["version"] == 1


@pytest.mark.parametrize("fields", [
    {},                                                         # nothing to change
    {"flexibility_consent": False},                              # equal to current
    {"earliest_departure": None, "latest_departure": None},      # explicit nulls = unchanged
    {"flexibility_consent": None},
    {"arrive_by": None},                                         # clearing an absent deadline
])
def test_patch_that_changes_nothing_is_a_noop(
    client, clock, alice, bob, landmarks, make_travel_request, test_session_factory, fields
):
    mine, theirs, sug, prop = _pending_pair(client, clock, alice, bob, landmarks, make_travel_request, test_session_factory)
    before = client.get(f"/api/campus/requests/{mine.id}", headers=alice[1]).json()
    resp = client.patch(f"/api/campus/requests/{mine.id}",
                        json={"expected_version": 1, **fields}, headers=alice[1])
    assert resp.status_code == 200, resp.text
    assert resp.json() == before and resp.json()["version"] == 1
    assert reload(test_session_factory, ConnectionProposal, prop).state == ProposalState.PENDING
    assert reload_or_none(test_session_factory, PairSuggestion, sug) is not None


def test_patch_with_equal_window_values_is_a_noop(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    resp = client.patch(
        f"/api/campus/requests/{req['id']}",
        json={"expected_version": 1,
              "earliest_departure": iso(clock.at(minutes=60)),
              "latest_departure": iso(clock.at(minutes=120))},
        headers=alice[1],
    )
    assert resp.status_code == 200 and resp.json()["version"] == 1


def test_noop_patch_still_checks_the_version(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    resp = client.patch(f"/api/campus/requests/{req['id']}", json={"expected_version": 9}, headers=alice[1])
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "stale_version"


def test_create_and_patch_lock_the_user_row_first(client, clock, alice, landmarks, monkeypatch):
    calls = []
    real = campus_request_service._lock_user
    monkeypatch.setattr(campus_request_service, "_lock_user",
                        lambda db, user: (calls.append(user.id), real(db, user))[1])
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    client.patch(f"/api/campus/requests/{req['id']}",
                 json={"expected_version": 1, "flexibility_consent": True}, headers=alice[1])
    assert calls == [alice[0].id, alice[0].id]


def test_patch_cannot_create_an_overlap_with_my_other_request(client, clock, alice, landmarks):
    create(client, alice[1], body(clock, landmarks, 60, 120))
    other = create(client, alice[1], body(clock, landmarks, 200, 260)).json()
    resp = client.patch(f"/api/campus/requests/{other['id']}",
                        json={"expected_version": 1, "earliest_departure": iso(clock.at(minutes=100))},
                        headers=alice[1])
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "overlapping_request"


def test_patch_only_open_requests(client, clock, alice, landmarks, make_travel_request):
    reserved = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, status="RESERVED")
    resp = client.patch(f"/api/campus/requests/{reserved.id}",
                        json={"expected_version": 1, "flexibility_consent": True}, headers=alice[1])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "request_not_open"


def _pending_pair(client, clock, alice, bob, landmarks, make_travel_request, test_session_factory):
    mine = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    theirs = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    low, high = campus_rules.pair_key(mine.id, theirs.id)
    sug = seed_suggestion(test_session_factory, low, high, clock)
    prop = seed_proposal(test_session_factory, clock, bob[0], alice[0], theirs, mine, suggestion_id=sug)
    return mine, theirs, sug, prop


def test_patch_expires_pending_proposals_and_deletes_suggestions(
    client, clock, alice, bob, landmarks, make_travel_request, test_session_factory
):
    mine, theirs, sug, prop = _pending_pair(client, clock, alice, bob, landmarks, make_travel_request, test_session_factory)
    resp = client.patch(f"/api/campus/requests/{mine.id}",
                        json={"expected_version": 1, "flexibility_consent": True}, headers=alice[1])
    assert resp.status_code == 200

    proposal = reload(test_session_factory, ConnectionProposal, prop)
    assert proposal.state == ProposalState.EXPIRED
    assert proposal.version == 2
    assert proposal.resolved_at == campus_time.to_db(clock.now)
    assert proposal.suggestion_id is None
    assert reload_or_none(test_session_factory, PairSuggestion, sug) is None
    # the other user's request is untouched
    other = reload(test_session_factory, TravelRequest, theirs.id)
    assert other.status == TravelRequestStatus.OPEN and other.version == 1


def reload_or_none(session_factory, model, row_id):
    db = session_factory()
    try:
        return db.get(model, row_id)
    finally:
        db.close()


# --------------------------------------------------------------------------
# DELETE
# --------------------------------------------------------------------------
def test_delete_cancels_and_is_idempotent(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    url = f"/api/campus/requests/{req['id']}"
    first = client.delete(url, headers=alice[1])
    assert first.status_code == 200
    assert first.json()["status"] == "CANCELLED" and first.json()["version"] == 2
    second = client.delete(url, headers=alice[1])
    assert second.status_code == 200
    assert second.json()["status"] == "CANCELLED" and second.json()["version"] == 2   # no second bump


def test_delete_expires_pending_proposals_and_deletes_suggestions(
    client, clock, alice, bob, landmarks, make_travel_request, test_session_factory
):
    mine, theirs, sug, prop = _pending_pair(client, clock, alice, bob, landmarks, make_travel_request, test_session_factory)
    assert client.delete(f"/api/campus/requests/{mine.id}", headers=alice[1]).status_code == 200
    assert reload(test_session_factory, ConnectionProposal, prop).state == ProposalState.EXPIRED
    assert reload_or_none(test_session_factory, PairSuggestion, sug) is None
    assert reload(test_session_factory, TravelRequest, theirs.id).status == TravelRequestStatus.OPEN


def test_delete_resolved_proposals_keep_their_state(
    client, clock, alice, bob, landmarks, make_travel_request, test_session_factory
):
    mine = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120)
    theirs = make_travel_request(bob[0], landmarks, start_offset_min=60, end_offset_min=120)
    declined = seed_proposal(test_session_factory, clock, bob[0], alice[0], theirs, mine, state=ProposalState.DECLINED)
    client.delete(f"/api/campus/requests/{mine.id}", headers=alice[1])
    assert reload(test_session_factory, ConnectionProposal, declined).state == ProposalState.DECLINED


def test_delete_reserved_request_must_use_party_cancel(client, clock, alice, landmarks, make_travel_request):
    reserved = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, status="RESERVED")
    resp = client.delete(f"/api/campus/requests/{reserved.id}", headers=alice[1])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "use_party_cancel"
    assert client.get(f"/api/campus/requests/{reserved.id}", headers=alice[1]).json()["status"] == "RESERVED"


@pytest.mark.parametrize("status", ["CANCELLED", "EXPIRED", "FULFILLED"])
def test_delete_on_terminal_request_is_200(client, clock, alice, landmarks, make_travel_request, status):
    row = make_travel_request(alice[0], landmarks, start_offset_min=60, end_offset_min=120, status=status)
    resp = client.delete(f"/api/campus/requests/{row.id}", headers=alice[1])
    assert resp.status_code == 200 and resp.json()["status"] == status


# --------------------------------------------------------------------------
# lazy expiry
# --------------------------------------------------------------------------
def test_expire_stale_expires_open_requests_and_pending_proposals(
    clock, alice, bob, landmarks, make_travel_request, test_session_factory
):
    old = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=40)
    fresh = make_travel_request(bob[0], landmarks, start_offset_min=10, end_offset_min=400)
    reserved = make_travel_request(alice[0], landmarks, start_offset_min=500, end_offset_min=520, status="RESERVED")
    prop_old = seed_proposal(test_session_factory, clock, bob[0], alice[0], fresh, old, minutes=20)
    prop_fresh = seed_proposal(test_session_factory, clock, alice[0], bob[0], reserved, fresh, minutes=300,
                               state=ProposalState.PENDING)

    clock.advance(minutes=45)
    db = test_session_factory()
    try:
        changed = campus_request_service.expire_stale(db, campus_time.utcnow())
        assert changed == 2          # the old request + its (already overdue) proposal
        db.commit()
    finally:
        db.close()

    expired = reload(test_session_factory, TravelRequest, old.id)
    assert expired.status == TravelRequestStatus.EXPIRED and expired.version == 2
    assert reload(test_session_factory, TravelRequest, fresh.id).status == TravelRequestStatus.OPEN
    assert reload(test_session_factory, TravelRequest, reserved.id).status == TravelRequestStatus.RESERVED
    p_old = reload(test_session_factory, ConnectionProposal, prop_old)
    assert p_old.state == ProposalState.EXPIRED and p_old.version == 2 and p_old.resolved_at is not None
    assert reload(test_session_factory, ConnectionProposal, prop_fresh).state == ProposalState.PENDING

    # nothing left to do
    db = test_session_factory()
    try:
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 0
    finally:
        db.close()


def test_expire_stale_expires_proposals_of_just_expired_requests(
    clock, alice, bob, landmarks, make_travel_request, test_session_factory
):
    mine = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=40)
    theirs = make_travel_request(bob[0], landmarks, start_offset_min=10, end_offset_min=400)
    prop = seed_proposal(test_session_factory, clock, bob[0], alice[0], theirs, mine, minutes=300)
    clock.advance(minutes=41)
    db = test_session_factory()
    try:
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 2
        db.commit()
    finally:
        db.close()
    assert reload(test_session_factory, ConnectionProposal, prop).state == ProposalState.EXPIRED


def test_expire_stale_is_commit_free(clock, alice, landmarks, make_travel_request, test_session_factory):
    old = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=40)
    clock.advance(minutes=60)
    db = test_session_factory()
    try:
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 1
        db.rollback()
    finally:
        db.close()
    assert reload(test_session_factory, TravelRequest, old.id).status == TravelRequestStatus.OPEN


def test_expire_boundary_is_inclusive(clock, alice, landmarks, make_travel_request, test_session_factory):
    row = make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=40)
    clock.advance(minutes=40)   # now == expires_at
    db = test_session_factory()
    try:
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 1
    finally:
        db.close()


def test_reads_lazily_expire_requests(client, clock, alice, landmarks):
    req = create(client, alice[1], body(clock, landmarks, 60, 120)).json()
    clock.advance(minutes=121)
    got = client.get(f"/api/campus/requests/{req['id']}", headers=alice[1]).json()
    assert got["status"] == "EXPIRED" and got["version"] == 2
    listed = client.get("/api/campus/requests?status=EXPIRED", headers=alice[1]).json()
    assert [r["id"] for r in listed] == [req["id"]]


def test_expire_stale_works_in_bounded_batches(clock, alice, landmarks, make_travel_request, test_session_factory, monkeypatch):
    monkeypatch.setattr(campus_request_service, "EXPIRE_BATCH_LIMIT", 2)
    rows = [make_travel_request(alice[0], landmarks, start_offset_min=10, end_offset_min=40) for _ in range(3)]
    clock.advance(minutes=60)
    db = test_session_factory()
    try:
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 2
        db.commit()
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 1
        db.commit()
        assert campus_request_service.expire_stale(db, campus_time.utcnow()) == 0
    finally:
        db.close()
    assert all(reload(test_session_factory, TravelRequest, r.id).status == TravelRequestStatus.EXPIRED for r in rows)


def test_status_expiry_index_exists_for_the_expiry_scan():
    index = next(i for i in TravelRequest.__table__.indexes if i.name == "ix_travel_requests_status_expires")
    assert [c.name for c in index.columns] == ["status", "expires_at"]
