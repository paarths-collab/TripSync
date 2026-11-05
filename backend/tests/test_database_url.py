"""Unit tests for DATABASE_URL normalization (app.db.database.normalize_database_url)."""

import pytest
from sqlalchemy import create_engine

from app.db.database import normalize_database_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Bare schemes are pinned to the psycopg2 driver pinned in requirements.txt.
        ("postgresql://u:p@127.0.0.1:1/db", "postgresql+psycopg2://u:p@127.0.0.1:1/db"),
        ("postgres://u:p@host.example.invalid:5432/db", "postgresql+psycopg2://u:p@host.example.invalid:5432/db"),
        # Credentials and query strings are preserved.
        (
            "postgresql://user:p%40ss%2Fword@host:5433/db?sslmode=require&connect_timeout=5",
            "postgresql+psycopg2://user:p%40ss%2Fword@host:5433/db?sslmode=require&connect_timeout=5",
        ),
        ("postgres://user:pw@host/db?sslmode=require", "postgresql+psycopg2://user:pw@host/db?sslmode=require"),
        # Explicit drivers are left alone.
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        # Non-Postgres URLs are left alone.
        ("sqlite:///./test.db", "sqlite:///./test.db"),
        ("sqlite://", "sqlite://"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_bare_postgresql_url_selects_psycopg2_driver():
    # create_engine does not connect, so no server is needed here.
    engine = create_engine(normalize_database_url("postgresql://u:p@127.0.0.1:1/db"))
    assert engine.dialect.driver == "psycopg2"
    engine.dispose()
