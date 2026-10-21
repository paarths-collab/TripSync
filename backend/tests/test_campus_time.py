"""campus_time helpers and the TimeOut schema helper."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core import campus_time
from app.schemas.campus_schema import TimeOut

UTC = timezone.utc
IST_NAME = "Asia/Kolkata"
NY_NAME = "America/New_York"


def test_utcnow_is_aware_utc():
    now = campus_time.utcnow()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)


def test_to_db_and_from_db_roundtrip():
    aware = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
    stored = campus_time.to_db(aware)
    assert stored.tzinfo is None and stored == datetime(2026, 3, 1, 18, 0)
    assert campus_time.from_db(stored) == aware
    assert campus_time.from_db(stored).tzinfo is not None


def test_to_db_converts_other_offsets_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert campus_time.to_db(datetime(2026, 3, 1, 23, 30, tzinfo=ist)) == datetime(2026, 3, 1, 18, 0)


def test_to_db_rejects_naive():
    with pytest.raises(ValueError):
        campus_time.to_db(datetime(2026, 3, 1, 18, 0))


def test_local_iso_rejects_naive():
    with pytest.raises(ValueError):
        campus_time.local_iso(datetime(2026, 3, 1, 18, 0), IST_NAME)


def test_parse_tz_valid_and_invalid():
    assert campus_time.parse_tz(IST_NAME).key == IST_NAME
    for bad in ("Mars/Olympus", "", " Asia/Kolkata", "../etc/passwd", None, 5):
        with pytest.raises(ValueError):
            campus_time.parse_tz(bad)


def test_local_rendering_in_kolkata_and_midnight_rollover():
    before = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)   # 23:30 IST, 1 March
    after = datetime(2026, 3, 1, 19, 0, tzinfo=UTC)    # 00:30 IST, 2 March
    assert campus_time.local_iso(before, IST_NAME) == "2026-03-01T23:30:00+05:30"
    assert campus_time.local_iso(after, IST_NAME) == "2026-03-02T00:30:00+05:30"


def test_local_rendering_across_new_york_spring_forward():
    # 2026-03-08: clocks jump 02:00 EST -> 03:00 EDT at 07:00 UTC.
    last_est = datetime(2026, 3, 8, 6, 59, tzinfo=UTC)
    first_edt = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    assert campus_time.local_iso(last_est, NY_NAME) == "2026-03-08T01:59:00-05:00"
    assert campus_time.local_iso(first_edt, NY_NAME) == "2026-03-08T03:00:00-04:00"
    # one real minute apart, two local clock hours' label apart
    assert first_edt - last_est == timedelta(minutes=1)


def test_local_rendering_across_new_york_fall_back():
    # 2026-11-01: 02:00 EDT -> 01:00 EST at 06:00 UTC (01:xx happens twice).
    first_pass = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    second_pass = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert campus_time.local_iso(first_pass, NY_NAME) == "2026-11-01T01:30:00-04:00"
    assert campus_time.local_iso(second_pass, NY_NAME) == "2026-11-01T01:30:00-05:00"


def test_midnight_rollover_in_new_york_on_dst_date():
    # 2026-03-08T04:30Z = 23:30 EST on the 7th; 05:30Z = 00:30 EST on the 8th.
    assert campus_time.local_iso(datetime(2026, 3, 8, 4, 30, tzinfo=UTC), NY_NAME).startswith("2026-03-07T23:30")
    assert campus_time.local_iso(datetime(2026, 3, 8, 5, 30, tzinfo=UTC), NY_NAME).startswith("2026-03-08T00:30")


def test_utc_iso_uses_z_suffix():
    assert campus_time.utc_iso(datetime(2026, 3, 1, 18, 0, tzinfo=UTC)) == "2026-03-01T18:00:00Z"
    assert campus_time.utc_iso(datetime(2026, 3, 1, 18, 0)) == "2026-03-01T18:00:00Z"  # stored naive UTC


def test_ceil_minute():
    on_minute = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    assert campus_time.ceil_minute(on_minute) == on_minute
    assert campus_time.ceil_minute(on_minute + timedelta(seconds=1)) == on_minute + timedelta(minutes=1)
    assert campus_time.ceil_minute(on_minute + timedelta(seconds=59, microseconds=1)) == on_minute + timedelta(minutes=1)
    with pytest.raises(ValueError):
        campus_time.ceil_minute(datetime(2026, 3, 1, 4, 0))


def test_time_out_helper_from_db_value():
    out = TimeOut.of(datetime(2026, 3, 1, 18, 0), IST_NAME)
    assert out.model_dump() == {
        "utc": "2026-03-01T18:00:00Z",
        "local": "2026-03-01T23:30:00+05:30",
        "timezone": IST_NAME,
    }
    assert TimeOut.of(None, IST_NAME) is None


def test_clock_fixture_patches_module_attribute(clock):
    assert campus_time.utcnow() == datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    clock.advance(minutes=90)
    assert campus_time.utcnow() == datetime(2026, 3, 1, 5, 30, tzinfo=UTC)
    clock.set(datetime(2026, 4, 1, tzinfo=UTC))
    assert campus_time.utcnow() == datetime(2026, 4, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        clock.set(datetime(2026, 4, 1))
