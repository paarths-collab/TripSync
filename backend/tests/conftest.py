"""Offline test harness for the TripSync FastAPI backend.

Everything here runs without network access and without Postgres:
- settings are built from fake env values set BEFORE any `app` import,
- the app's engine is swapped for an in-memory SQLite database,
- the `get_db` dependency is overridden to use that database,
- outbound httpx.AsyncClient calls raise immediately.
"""

import os

# --- Fake environment. Must run before anything imports `app` because
# app.core.config.settings is constructed at import time. Direct assignment
# (not setdefault) so a developer's real shell env never leaks in.
os.environ["DATABASE_URL"] = "sqlite:///./.pytest_tripsync.db"  # never connected to; tests override the engine
os.environ["ALLOW_ORIGINS"] = "*"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-for-production"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["OLA_MAPS_API_KEY"] = "test-ola-key-SENTINEL"
os.environ.pop("OLA_MAPS_PROXY", None)

import bcrypt  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    """SQLite has no JSONB; render it as JSON so create_all works in tests."""
    return "JSON"


from app import main as app_main  # noqa: E402
from app.core.ws_manager import manager  # noqa: E402
from app.db import database as app_database  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import profile_model, user_model  # noqa: E402
from app.services import auth_service, pooling_service  # noqa: E402

TEST_PASSWORD = "test-password-not-real"
SENTINEL_OLA_KEY = os.environ["OLA_MAPS_API_KEY"]


# --------------------------------------------------------------------------
# Network blocking
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Make every async httpx request fail loudly.

    Only AsyncClient.send is patched: Starlette's TestClient subclasses the
    sync httpx.Client and goes through Client.send, so patching that would
    break the harness itself. Provider calls (pooling_service, map_service)
    all use httpx.AsyncClient.
    """

    async def _blocked_send(self, *args, **kwargs):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(httpx.AsyncClient, "send", _blocked_send)


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
@pytest.fixture
def test_engine():
    """Fresh in-memory SQLite engine with the full schema, per test."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def _wire_app_to_test_db(monkeypatch, test_engine, test_session_factory):
    """Point the app at the test database for every test.

    - get_db (imported by name into every router) is overridden.
    - main.engine (used by the lifespan create_all) and database.SessionLocal
      (used by get_db's default body) are repointed defensively.
    """

    def _override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(app_main, "engine", test_engine)
    monkeypatch.setattr(app_database, "SessionLocal", test_session_factory)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def db_session(test_session_factory):
    """A short-lived session for seeding or inspecting rows directly.

    Each helper commits and closes its own session, so no transaction is left
    open on the shared StaticPool connection while the app is handling requests.
    """
    db = test_session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def college(test_session_factory):
    """A College row (name taken from the app's ALLOWED_COLLEGES list)."""
    db = test_session_factory()
    try:
        row = user_model.College(name="DJSCE")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


@pytest.fixture
def make_user(test_session_factory):
    """Factory: make_user(email, full_name, college, phone=None) -> (user, auth_headers).

    Creates the User directly in the test DB with a bcrypt-hashed password (the
    same algorithm as user_service.create_user; low cost factor for speed) and,
    if a phone is given, a Profile row holding it (phone is not a User column).
    auth_headers come from the app's own auth_service.create_access_token.
    """

    def _make_user(email, full_name, college, phone=None):
        hashed = bcrypt.hashpw(
            TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=4)
        ).decode("utf-8")
        db = test_session_factory()
        try:
            user = user_model.User(
                email=email,
                full_name=full_name,
                hashed_password=hashed,
                college_id=college.id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            if phone is not None:
                db.add(profile_model.Profile(user_id=user.id, phone_number=phone))
                db.commit()
            token = auth_service.create_access_token(data={"sub": user.email})
            headers = {"Authorization": f"Bearer {token}"}
            return user, headers
        finally:
            db.close()

    return _make_user


# --------------------------------------------------------------------------
# HTTP client and fakes
# --------------------------------------------------------------------------
@pytest.fixture
def client():
    """TestClient without `with`, so the app lifespan (Postgres create_all) never runs."""
    return TestClient(app)


@pytest.fixture
def ws_sent(monkeypatch):
    """Records WebSocket pushes instead of sending them.

    Yields a list of (user_id, message) tuples in call order.
    """
    sent = []

    async def _record(message, user_id):
        sent.append((user_id, message))

    monkeypatch.setattr(manager, "send_personal_message", _record)
    yield sent


@pytest.fixture
def fake_distance_matrix(monkeypatch):
    """Installs a fake for the Ola distance-matrix helper used by pooling matching.

    Usage:
        async def fake(origin, destinations):  # tuples of (lat, lng)
            return [1000.0 for _ in destinations]
        fake_distance_matrix(fake)

    The fake must be async and return one float (or None) per destination.
    """

    def _install(fn):
        monkeypatch.setattr(pooling_service, "_get_distances_from_ola", fn)
        return fn

    return _install


# --------------------------------------------------------------------------
# Campus scheduling fixtures
# --------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.core import campus_time  # noqa: E402
from app.models import campus_model  # noqa: E402

DEFAULT_CLOCK_START = datetime(2026, 3, 1, 4, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    """Settable clock. `campus_time.utcnow()` returns `.now` while installed."""

    def __init__(self, start=DEFAULT_CLOCK_START):
        self.now = start

    def __call__(self):
        return self.now

    def set(self, dt):
        if dt.tzinfo is None:
            raise ValueError("FakeClock.set needs an aware datetime")
        self.now = dt.astimezone(timezone.utc)
        return self.now

    def advance(self, **kwargs):
        """advance(minutes=5), advance(hours=1, seconds=3), ..."""
        self.now = self.now + timedelta(**kwargs)
        return self.now

    def at(self, **offset):
        """A time relative to the current fake now, e.g. clock.at(minutes=30)."""
        return self.now + timedelta(**offset)


@pytest.fixture
def clock(monkeypatch):
    """Fake clock patched into campus_time.utcnow (default 2026-03-01T04:00:00Z)."""
    fake = FakeClock()
    monkeypatch.setattr(campus_time, "utcnow", fake)
    return fake


@pytest.fixture
def landmarks(test_session_factory, college):
    """Landmarks of the `college` fixture's college.

    Returns {"campus": Main Gate (CAMPUS_POINT), "hub": Airport Terminal (HUB),
    "campus2": Library (CAMPUS_POINT)} as detached, fully loaded rows.
    """
    db = test_session_factory()
    try:
        rows = {
            "campus": campus_model.CampusLandmark(
                college_id=college.id, name="Main Gate",
                kind=campus_model.LandmarkKind.CAMPUS_POINT,
                latitude=19.1000, longitude=72.8400, timezone="Asia/Kolkata", active=True,
            ),
            "hub": campus_model.CampusLandmark(
                college_id=college.id, name="Airport Terminal",
                kind=campus_model.LandmarkKind.HUB,
                latitude=19.0900, longitude=72.8700, timezone="Asia/Kolkata", active=True,
            ),
            "campus2": campus_model.CampusLandmark(
                college_id=college.id, name="Library",
                kind=campus_model.LandmarkKind.CAMPUS_POINT,
                latitude=19.1010, longitude=72.8410, timezone="Asia/Kolkata", active=True,
            ),
        }
        db.add_all(rows.values())
        db.commit()
        for row in rows.values():
            db.refresh(row)
        return rows
    finally:
        db.close()


@pytest.fixture
def make_travel_request(test_session_factory, clock):
    """Factory building a TravelRequest relative to the fake clock.

    make_travel_request(user, landmarks, *, start_offset_min, end_offset_min,
        direction="TO_HUB", flexibility=False, arrive_by=None, status="OPEN",
        created_ago_min=0)
    - window = [clock.now + start_offset_min, clock.now + end_offset_min]
    - corridor is always landmarks["campus"] <-> landmarks["hub"]
    - arrive_by: None, an aware datetime, or minutes (int/float) after clock.now
    - created_at = clock.now - created_ago_min, independent of departure times
    - expires_at = latest_departure
    Returns a detached, refreshed row.
    """

    def _make(
        user, landmarks, *, start_offset_min, end_offset_min, direction="TO_HUB",
        flexibility=False, arrive_by=None, status="OPEN", created_ago_min=0,
    ):
        now = clock.now
        earliest = now + timedelta(minutes=start_offset_min)
        latest = now + timedelta(minutes=end_offset_min)
        if isinstance(arrive_by, (int, float)):
            arrive_by = now + timedelta(minutes=arrive_by)
        db = test_session_factory()
        try:
            row = campus_model.TravelRequest(
                user_id=user.id,
                college_id=user.college_id,
                mode=campus_model.TravelMode.SHARED_TAXI_PARTY,
                origin_landmark_id=landmarks["campus"].id,
                hub_id=landmarks["hub"].id,
                direction=campus_model.Direction(direction),
                earliest_departure=campus_time.to_db(earliest),
                latest_departure=campus_time.to_db(latest),
                arrive_by=campus_time.to_db(arrive_by) if arrive_by is not None else None,
                timezone="Asia/Kolkata",
                flexibility_consent=flexibility,
                expires_at=campus_time.to_db(latest),
                status=campus_model.TravelRequestStatus(status),
                version=1,
                created_at=campus_time.to_db(now - timedelta(minutes=created_ago_min)),
                updated_at=campus_time.to_db(now),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            db.close()

    return _make


class WsDelivery:
    """Recorder replacing manager.send_personal_message.

    `.sent` holds (user_id, message) for messages that were "delivered"
    (return 1); `.attempts` holds every call. The recorder is also iterable /
    indexable / sized over `.sent`. fail_for(user_id) / fail_all() make sends
    return 0 (nothing recorded in `.sent`); restore() delivers again.
    """

    def __init__(self):
        self.sent = []
        self.attempts = []
        self._fail_all = False
        self._fail_users = set()

    def fail_for(self, user_id):
        self._fail_users.add(user_id)

    def fail_all(self):
        self._fail_all = True

    def restore(self):
        self._fail_all = False
        self._fail_users.clear()

    async def __call__(self, message, user_id):
        self.attempts.append((user_id, message))
        if self._fail_all or user_id in self._fail_users:
            return 0
        self.sent.append((user_id, message))
        return 1

    def __iter__(self):
        return iter(self.sent)

    def __len__(self):
        return len(self.sent)

    def __getitem__(self, i):
        return self.sent[i]


@pytest.fixture
def ws_delivery(monkeypatch):
    """Patches manager.send_personal_message with a WsDelivery recorder (returns 1/0)."""
    recorder = WsDelivery()
    monkeypatch.setattr(manager, "send_personal_message", recorder)
    return recorder


def _auth_jwt(headers):
    return headers["Authorization"].removeprefix("Bearer ")


@pytest.fixture
def auth_jwt():
    """auth_jwt(headers) -> the raw JWT from an Authorization: Bearer header."""
    return _auth_jwt
