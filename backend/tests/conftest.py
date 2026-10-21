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
