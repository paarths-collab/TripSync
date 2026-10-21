"""Pure campus rules: window validation, overlap, eligibility, deadlines."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core import campus_rules as rules

UTC = timezone.utc
NOW = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)


def at(minutes):
    return NOW + timedelta(minutes=minutes)


def req(start, end, *, user_id=1, college_id=1, origin=10, hub=20, direction="TO_HUB",
        status="OPEN", flex=False, expires=None, arrive_by=None, mode="SHARED_TAXI_PARTY",
        created_at=None):
    return SimpleNamespace(
        user_id=user_id, college_id=college_id, mode=mode,
        origin_landmark_id=origin, hub_id=hub, direction=direction, status=status,
        earliest_departure=at(start), latest_departure=at(end),
        expires_at=expires if expires is not None else at(end),
        flexibility_consent=flex, arrive_by=arrive_by, created_at=created_at,
    )


# --- validate_window --------------------------------------------------------
def test_validate_window_accepts_typical_window():
    rules.validate_window(at(60), at(120), NOW)


@pytest.mark.parametrize("minutes,ok", [(9, False), (10, True), (11, True)])
def test_validate_window_min_length_boundary(minutes, ok):
    if ok:
        rules.validate_window(at(60), at(60 + minutes), NOW)
    else:
        with pytest.raises(ValueError, match=rules.ERR_TOO_SHORT):
            rules.validate_window(at(60), at(60 + minutes), NOW)


def test_validate_window_max_length_boundary():
    rules.validate_window(at(60), at(60 + 6 * 60), NOW)
    with pytest.raises(ValueError, match=rules.ERR_TOO_LONG):
        rules.validate_window(at(60), at(60 + 6 * 60) + timedelta(seconds=1), NOW)


def test_validate_window_order():
    with pytest.raises(ValueError, match=rules.ERR_ORDER):
        rules.validate_window(at(120), at(60), NOW)
    with pytest.raises(ValueError, match=rules.ERR_ORDER):
        rules.validate_window(at(60), at(60), NOW)


def test_validate_window_latest_must_be_after_now():
    with pytest.raises(ValueError, match=rules.ERR_ALREADY_ENDED):
        rules.validate_window(at(-60), at(0), NOW)       # ends exactly now
    with pytest.raises(ValueError, match=rules.ERR_ALREADY_ENDED):
        rules.validate_window(at(-120), at(-60), NOW)
    rules.validate_window(at(-60), at(0) + timedelta(seconds=1), NOW)  # already underway is fine


def test_validate_window_lead_time_boundary():
    far = NOW + timedelta(days=rules.MAX_LEAD_DAYS)
    rules.validate_window(far, far + timedelta(hours=1), NOW)
    with pytest.raises(ValueError, match=rules.ERR_TOO_FAR):
        rules.validate_window(far + timedelta(seconds=1), far + timedelta(hours=1), NOW)


def test_validate_window_rejects_naive():
    naive = datetime(2026, 3, 1, 6, 0)
    with pytest.raises(ValueError, match=rules.ERR_NAIVE):
        rules.validate_window(naive, at(120), NOW)
    with pytest.raises(ValueError, match=rules.ERR_NAIVE):
        rules.validate_window(at(60), naive, NOW)
    with pytest.raises(ValueError, match=rules.ERR_NAIVE):
        rules.validate_window(at(60), at(120), naive)


def test_validate_window_accepts_non_utc_offsets():
    ist = timezone(timedelta(hours=5, minutes=30))
    rules.validate_window(at(60).astimezone(ist), at(120).astimezone(ist), NOW)


# --- windows_overlap --------------------------------------------------------
def test_windows_overlap_basic_and_contained():
    assert rules.windows_overlap(at(0), at(60), at(30), at(90)) == (at(30), at(60))
    assert rules.windows_overlap(at(0), at(100), at(20), at(40)) == (at(20), at(40))


def test_windows_overlap_touching_is_a_single_instant():
    assert rules.windows_overlap(at(0), at(180), at(180), at(300)) == (at(180), at(180))
    assert rules.windows_overlap(at(180), at(300), at(0), at(180)) == (at(180), at(180))


def test_windows_overlap_one_second_gap_is_none():
    gap = timedelta(seconds=1)
    assert rules.windows_overlap(at(0), at(60), at(60) + gap, at(120)) is None


# --- eligible_pair ----------------------------------------------------------
def pair(a_kwargs=None, b_kwargs=None, a_win=(60, 120), b_win=(90, 150)):
    a = req(*a_win, user_id=1, **(a_kwargs or {}))
    b = req(*b_win, user_id=2, **(b_kwargs or {}))
    return a, b


def test_overlapping_windows_are_eligible_with_feasible_window():
    a, b = pair()
    e = rules.eligible_pair(a, b, NOW)
    assert e.ok and e.reason == "WINDOW_OVERLAP"
    assert (e.feasible_start, e.feasible_end) == (at(90), at(120))
    assert rules.eligible_pair(b, a, NOW) == e   # symmetric


def test_touching_windows_are_eligible():
    a, b = pair(a_win=(60, 120), b_win=(120, 180))
    e = rules.eligible_pair(a, b, NOW)
    assert e.ok and e.feasible_start == e.feasible_end == at(120)


def test_one_second_gap_not_eligible_without_flex():
    a = req(60, 120, user_id=1)
    b = req(0, 0, user_id=2)
    b.earliest_departure = at(120) + timedelta(seconds=1)
    b.latest_departure = at(180)
    b.expires_at = at(180)
    e = rules.eligible_pair(a, b, NOW)
    assert not e.ok and e.reason == "disjoint_windows"
    assert e.feasible_start is None and e.feasible_end is None


def test_same_user_not_eligible():
    a, b = pair()
    b.user_id = a.user_id
    assert rules.eligible_pair(a, b, NOW).reason == "different_user"


def test_different_college():
    a, b = pair(b_kwargs={"college_id": 2})
    assert rules.eligible_pair(a, b, NOW).reason == "different_college"


def test_opposite_direction():
    a, b = pair(b_kwargs={"direction": "FROM_HUB"})
    e = rules.eligible_pair(a, b, NOW)
    assert not e.ok and e.reason == "opposite_direction"


@pytest.mark.parametrize("override", [{"origin": 11}, {"hub": 21}, {"mode": "OTHER"}])
def test_different_corridor(override):
    a, b = pair(b_kwargs=override)
    assert rules.eligible_pair(a, b, NOW).reason == "different_corridor"


@pytest.mark.parametrize("status", ["RESERVED", "FULFILLED", "CANCELLED", "EXPIRED"])
def test_not_open_either_side(status):
    a, b = pair(b_kwargs={"status": status})
    assert rules.eligible_pair(a, b, NOW).reason == "not_open"
    a, b = pair(a_kwargs={"status": status})
    assert rules.eligible_pair(a, b, NOW).reason == "not_open"


def test_enum_like_values_are_accepted():
    class V:  # stands in for a str-Enum member
        def __init__(self, value): self.value = value
    a, b = pair(a_kwargs={"status": V("OPEN"), "direction": V("TO_HUB")},
                b_kwargs={"status": V("OPEN"), "direction": V("TO_HUB")})
    assert rules.eligible_pair(a, b, NOW).ok


def test_expired_by_expires_at_or_by_latest_departure():
    a, b = pair(b_kwargs={"expires": at(0)})            # expires exactly now
    assert rules.eligible_pair(a, b, NOW).reason == "expired"
    a, b = pair(b_kwargs={"expires": at(-5)})
    assert rules.eligible_pair(a, b, NOW).reason == "expired"
    a, b = pair(b_win=(-60, 0))                          # window ended exactly now
    assert rules.eligible_pair(a, b, NOW).reason == "expired"
    a, b = pair(b_win=(-60, 1))                          # one minute left
    assert rules.eligible_pair(a, b, NOW).reason == "disjoint_windows"   # not expired, just disjoint


def test_expiry_is_evaluated_against_now_argument():
    a, b = pair()
    assert rules.eligible_pair(a, b, NOW).ok
    assert rules.eligible_pair(a, b, at(121)).reason == "expired"


def test_flexibility_requires_mutual_consent():
    # gap of 40 minutes between windows: [60,120] and [160,220]
    a, b = pair(a_win=(60, 120), b_win=(160, 220))
    assert rules.eligible_pair(a, b, NOW).reason == "disjoint_windows"
    a.flexibility_consent = b.flexibility_consent = True
    e = rules.eligible_pair(a, b, NOW)
    assert e.ok and e.reason == "FLEXIBLE_WINDOW"
    # overlap of extended windows [30,150] and [130,250] -> [130,150]
    assert (e.feasible_start, e.feasible_end) == (at(130), at(150))


@pytest.mark.parametrize("a_flex,b_flex", [(True, False), (False, True), (False, False)])
def test_one_sided_or_no_consent_gives_no_flexible_match(a_flex, b_flex):
    a, b = pair(a_win=(60, 120), b_win=(160, 220))
    a.flexibility_consent, b.flexibility_consent = a_flex, b_flex
    assert rules.eligible_pair(a, b, NOW).reason == "disjoint_windows"


def test_flexibility_gap_boundaries():
    flex = rules.FLEX_MINUTES
    a, b = pair(a_win=(60, 120), b_win=(120 + 2 * flex, 300))
    a.flexibility_consent = b.flexibility_consent = True
    e = rules.eligible_pair(a, b, NOW)          # gap == 2*FLEX touches at one instant
    assert e.ok and e.reason == "FLEXIBLE_WINDOW" and e.feasible_start == e.feasible_end
    b.earliest_departure += timedelta(seconds=1)
    assert rules.eligible_pair(a, b, NOW).reason == "disjoint_windows"


def test_direct_overlap_wins_over_flexible_reason():
    a, b = pair(a_kwargs={"flex": True}, b_kwargs={"flex": True})
    assert rules.eligible_pair(a, b, NOW).reason == "WINDOW_OVERLAP"


def test_creation_time_is_never_consulted():
    a, b = pair()
    del_a = SimpleNamespace(**vars(a))
    del del_a.created_at          # attribute absent entirely: would raise if read
    del_b = SimpleNamespace(**vars(b))
    del del_b.created_at
    assert rules.eligible_pair(del_a, del_b, NOW).ok
    # And a wildly different creation time changes nothing.
    a.created_at, b.created_at = NOW - timedelta(days=30), NOW + timedelta(days=30)
    assert rules.eligible_pair(a, b, NOW).ok


def test_same_creation_time_but_hours_apart_departures_not_eligible():
    a, b = pair(a_win=(60, 120), b_win=(360, 420))
    a.created_at = b.created_at = NOW
    assert rules.eligible_pair(a, b, NOW).reason == "disjoint_windows"


def test_naive_db_values_are_read_as_utc():
    a, b = pair()
    for r in (a, b):
        r.earliest_departure = r.earliest_departure.replace(tzinfo=None)
        r.latest_departure = r.latest_departure.replace(tzinfo=None)
        r.expires_at = r.expires_at.replace(tzinfo=None)
    e = rules.eligible_pair(a, b, NOW)
    assert e.ok and e.feasible_start == at(90) and e.feasible_start.tzinfo is not None


def test_midnight_rollover_in_campus_local_time_overlaps():
    # 23:30-00:30 IST vs 00:00-01:00 IST across midnight (IST = UTC+5:30)
    base = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)   # 23:30 IST
    a = req(0, 0, user_id=1); b = req(0, 0, user_id=2)
    a.earliest_departure, a.latest_departure = base, base + timedelta(hours=1)
    b.earliest_departure, b.latest_departure = base + timedelta(minutes=30), base + timedelta(minutes=90)
    a.expires_at, b.expires_at = a.latest_departure, b.latest_departure
    e = rules.eligible_pair(a, b, base - timedelta(hours=1))
    assert e.ok
    from app.core import campus_time
    assert campus_time.local_iso(e.feasible_start, "Asia/Kolkata").startswith("2026-03-02T00:00")
    assert campus_time.local_iso(e.feasible_end, "Asia/Kolkata").startswith("2026-03-02T00:30")


# --- deadline_warnings ------------------------------------------------------
def est(status, duration=None):
    return SimpleNamespace(status=status, duration_s=duration)


def test_no_deadline_no_warning():
    a, b = pair()
    assert rules.deadline_warnings(a, b, at(120), est("VERIFIED", 600)) == []
    assert rules.deadline_warnings(a, b, at(120), est("UNVERIFIED")) == []


def test_verified_estimate_that_misses_deadline_warns():
    a, b = pair(a_kwargs={"arrive_by": at(120) + timedelta(minutes=30)})
    assert rules.deadline_warnings(a, b, at(120), est("VERIFIED", 31 * 60)) == ["cannot_meet_arrive_by"]
    assert rules.deadline_warnings(a, b, at(120), est("VERIFIED", 30 * 60)) == []   # arrives exactly on time
    # either request's deadline counts
    a, b = pair(b_kwargs={"arrive_by": at(120) + timedelta(minutes=10)})
    assert rules.deadline_warnings(a, b, at(120), est("VERIFIED", 11 * 60)) == ["cannot_meet_arrive_by"]


def test_unverified_estimate_with_deadline_warns_unverified():
    a, b = pair(a_kwargs={"arrive_by": at(300)})
    assert rules.deadline_warnings(a, b, at(120), est("UNVERIFIED")) == ["deadline_unverified"]
    assert rules.deadline_warnings(a, b, at(120), None) == ["deadline_unverified"]
    assert rules.deadline_warnings(a, b, at(120), {"status": "UNVERIFIED", "duration_s": None}) == ["deadline_unverified"]


def test_deadline_warnings_accept_mapping_and_enum_status():
    a, b = pair(a_kwargs={"arrive_by": at(121)})
    assert rules.deadline_warnings(a, b, at(120), {"status": "VERIFIED", "duration_s": 120}) == ["cannot_meet_arrive_by"]
    from app.models.campus_model import EstimateStatus
    assert rules.deadline_warnings(a, b, at(120), est(EstimateStatus.VERIFIED, 30)) == []


def test_deadline_uses_earliest_feasible_departure_not_window_end():
    """A party leaves at the earliest feasible instant: a window that ends late
    must not trigger a warning when leaving at its start still meets the deadline."""
    deadline = at(60) + timedelta(minutes=45)
    a, b = pair(a_kwargs={"arrive_by": deadline})
    duration = est("VERIFIED", 40 * 60)
    # leaving at +60 min arrives at +100, before the +105 deadline
    assert rules.deadline_warnings(a, b, earliest_feasible_departure=at(60), estimate=duration) == []
    # the window END (+180) would have been too late; that is no longer the test
    assert rules.deadline_warnings(a, b, earliest_feasible_departure=at(180), estimate=duration) == [
        "cannot_meet_arrive_by"
    ]


# --- small helpers ----------------------------------------------------------
def test_pair_key_orders_ids():
    assert rules.pair_key(9, 3) == (3, 9) and rules.pair_key(3, 9) == (3, 9)


def test_agreed_departure_clamps_to_now_rounded_up():
    start, end = at(0), at(60)
    now = NOW + timedelta(minutes=10, seconds=20)
    assert rules.agreed_departure(start, end, now) == at(11)
    assert rules.agreed_departure(at(30), end, now) == at(30)           # window start still ahead
    assert rules.agreed_departure(start, end, NOW + timedelta(minutes=10)) == at(10)  # exact minute
    assert rules.agreed_departure(start, end, at(60) + timedelta(seconds=1)) is None
    assert rules.agreed_departure(start, end, at(60)) == at(60)


def test_proposal_expiry_is_capped_by_earlier_departure_end():
    a, b = pair(a_win=(5, 10), b_win=(5, 100))
    assert rules.proposal_expires_at(NOW, a, b) == at(10)
    a, b = pair(a_win=(5, 200), b_win=(5, 100))
    assert rules.proposal_expires_at(NOW, a, b) == at(rules.PROPOSAL_TTL_MINUTES)


def test_resolve_request_expiry():
    assert rules.resolve_request_expiry(at(120), None) == at(120)
    assert rules.resolve_request_expiry(at(120), at(100)) == at(100)
    assert rules.resolve_request_expiry(at(120), at(500)) == at(180)


def test_backoff_is_exponential_and_capped():
    assert [rules.backoff_seconds(n) for n in range(0, 4)] == [5, 10, 20, 40]
    assert rules.backoff_seconds(20) == rules.OUTBOX_BACKOFF_MAX_SECONDS


def test_constants_match_spec():
    assert rules.RULE_VERSION == "window-overlap-v1"
    assert (rules.MAX_WINDOW_HOURS, rules.MAX_LEAD_DAYS, rules.MIN_WINDOW_MINUTES, rules.FLEX_MINUTES) == (6, 14, 10, 30)
    assert (rules.MAX_OPEN_REQUESTS_PER_USER, rules.PROPOSAL_TTL_MINUTES, rules.SUGGESTION_TTL_MINUTES) == (3, 30, 15)
    assert (rules.RECENT_ENDED_HOURS, rules.ESTIMATE_TTL_MINUTES, rules.ESTIMATE_RETRY_SECONDS) == (24, 360, 60)
    assert (rules.OUTBOX_MAX_ATTEMPTS, rules.OUTBOX_BACKOFF_BASE_SECONDS, rules.OUTBOX_BACKOFF_MAX_SECONDS) == (8, 5, 300)
    assert "not a booking, dispatch or safety guarantee" in rules.TRANSPORT_RESPONSIBILITY_TEXT


# --- with real ORM rows built by the conftest fixtures -----------------------
def test_orm_rows_created_an_hour_apart_still_match(clock, college, landmarks, make_user, make_travel_request):
    u1, _ = make_user("a1@example.test", "A One", college)
    u2, _ = make_user("a2@example.test", "A Two", college)
    r1 = make_travel_request(u1, landmarks, start_offset_min=180, end_offset_min=240, created_ago_min=90)
    r2 = make_travel_request(u2, landmarks, start_offset_min=200, end_offset_min=260, created_ago_min=0)
    assert rules.eligible_pair(r1, r2, clock()).ok


def test_orm_rows_created_together_but_departing_hours_apart_do_not_match(
    clock, college, landmarks, make_user, make_travel_request
):
    u1, _ = make_user("b1@example.test", "B One", college)
    u2, _ = make_user("b2@example.test", "B Two", college)
    r1 = make_travel_request(u1, landmarks, start_offset_min=60, end_offset_min=120)
    r2 = make_travel_request(u2, landmarks, start_offset_min=360, end_offset_min=420)
    assert rules.eligible_pair(r1, r2, clock()).reason == "disjoint_windows"
