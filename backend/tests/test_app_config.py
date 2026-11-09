"""App wiring: CORS options, app name, readiness probe and startup database work."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main as app_main
from app.core.config import Settings, settings
from app.db.database import get_db
from app.main import app
from app.models import user_model
from app.services import college_service

BASE_ENV = {
    "ALLOW_ORIGINS": "*",
    "JWT_SECRET_KEY": "x",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    "OLA_MAPS_API_KEY": "x",
}


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
def test_wildcard_origins_disable_credentials():
    options = app_main.cors_options("*")
    assert options["allow_origins"] == ["*"]
    assert options["allow_credentials"] is False


def test_explicit_origins_allow_credentials():
    options = app_main.cors_options(" https://app.example.invalid ,http://localhost:8081,, ")
    assert options["allow_origins"] == ["https://app.example.invalid", "http://localhost:8081"]
    assert options["allow_credentials"] is True


def test_empty_origins_allow_nothing():
    assert app_main.cors_options("") == {
        "allow_origins": [], "allow_credentials": False, "allow_methods": ["*"], "allow_headers": ["*"],
    }


def test_app_cors_preflight_uses_setting(client):
    # The test environment sets ALLOW_ORIGINS="*".
    response = client.options("/api/health/ping", headers={
        "Origin": "https://anywhere.example.invalid",
        "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


def test_app_title_and_root_use_app_name(client):
    assert app.title == f"{settings.APP_NAME} API"
    assert client.get("/").json() == {"message": "TripSync API is running!"}


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------
def test_ready_when_database_answers(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_not_ready_when_database_fails(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        def rollback(self):
            pass

        def close(self):
            pass

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = client.get("/api/health/ready")
    finally:
        app.dependency_overrides[get_db] = previous
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}


# --------------------------------------------------------------------------
# DB_AUTO_CREATE and startup
# --------------------------------------------------------------------------
@pytest.mark.parametrize("url, override, expected", [
    ("sqlite:///./dev.db", None, True),
    ("postgresql+psycopg2://u:p@host/db", None, False),
    ("postgresql+psycopg2://u:p@host/db", "true", True),
    ("sqlite:///./dev.db", "false", False),
])
def test_db_auto_create_defaults(monkeypatch, url, override, expected):
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_URL", url)
    if override is None:
        monkeypatch.delenv("DB_AUTO_CREATE", raising=False)
    else:
        monkeypatch.setenv("DB_AUTO_CREATE", override)
    assert Settings(_env_file=None).db_auto_create is expected


def test_startup_syncs_colleges(test_session_factory):
    with TestClient(app):
        pass
    with test_session_factory() as db:
        rows = {c.name: c.email_domains for c in db.query(user_model.College).all()}
    assert set(rows) == set(college_service.ALLOWED_COLLEGES)
    assert rows["DJSCE"] == ["djsce.ac.in"]


def test_startup_without_auto_create_skips_create_all(monkeypatch, test_session_factory):
    calls = []
    monkeypatch.setattr(settings, "DB_AUTO_CREATE", False)
    monkeypatch.setattr(app_main, "create_db_and_tables", lambda: calls.append("create"))
    app_main.prepare_database()
    assert calls == []
    with test_session_factory() as db:
        assert db.query(user_model.College).count() == len(college_service.ALLOWED_COLLEGES)
