"""Alembic migrations: the head revision must build exactly the models' schema.

The SQLite tests always run. The PostgreSQL variant runs when
TRIPSYNC_TEST_PG_URL is set (inside a throwaway schema, like the other
Postgres tests).
"""

import os
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import schema as db_schema
from app.db.database import Base
from app.models import load_all_models

load_all_models()

PG_URL = os.environ.get("TRIPSYNC_TEST_PG_URL")


def _config(url: str | None = None, connection=None) -> Config:
    config = Config(db_schema.ALEMBIC_INI)
    config.set_main_option("script_location", db_schema.MIGRATIONS_DIR)
    config.attributes["configure_logger"] = False  # keep pytest's logging intact
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _diff(connection) -> list:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(context, Base.metadata)


def test_single_linear_history():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1
    revisions = [rev.revision for rev in script.walk_revisions()]
    assert revisions[-1] == "0001_baseline"
    assert script.get_current_head() == db_schema.alembic_head()


def test_sqlite_head_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path}/migrated.db"
    command.upgrade(_config(url), "head")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            assert _diff(connection) == []
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == db_schema.alembic_head()
    finally:
        engine.dispose()


def test_sqlite_downgrade_to_base_and_back(tmp_path):
    url = f"sqlite:///{tmp_path}/roundtrip.db"
    command.upgrade(_config(url), "head")
    command.downgrade(_config(url), "base")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
    command.upgrade(_config(url), "head")


def test_phase1_revision_lowercases_emails_without_collisions(tmp_path):
    url = f"sqlite:///{tmp_path}/legacy.db"
    command.upgrade(_config(url), "0001_baseline")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO colleges (id, name) VALUES (1, 'DJSCE')"))
            connection.execute(text(
                "INSERT INTO users (email, hashed_password, full_name, college_id) VALUES "
                "('Mixed.Case@Example.com', 'x', 'A', 1), (' padded@example.com ', 'x', 'B', 1), "
                "('dup@example.com', 'x', 'C', 1), ('DUP@example.com', 'x', 'D', 1)"
            ))
        command.upgrade(_config(url), "head")
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT email, token_version, is_active, email_verified_at, date_of_birth FROM users ORDER BY id"
            )).all()
            domains = connection.execute(text("SELECT email_domains FROM colleges")).scalar_one()
    finally:
        engine.dispose()
    assert [r.email for r in rows] == [
        "mixed.case@example.com", "padded@example.com", "dup@example.com", "DUP@example.com",
    ]
    # Existing accounts: not revoked, active, unverified (they verify at next login).
    assert all(r.token_version == 0 and r.is_active and r.email_verified_at is None for r in rows)
    assert all(r.date_of_birth is None for r in rows)
    assert domains == "[]"


def test_auto_create_on_empty_sqlite_stamps_head(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/dev.db")
    try:
        db_schema.auto_create_schema(engine)
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == db_schema.alembic_head()
            assert _diff(connection) == []
        # A second start is a no-op (and does not re-stamp or fail).
        db_schema.auto_create_schema(engine)
    finally:
        engine.dispose()


def test_auto_create_on_existing_tables_does_not_stamp(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY)"))
        db_schema.auto_create_schema(engine)
        assert "alembic_version" not in inspect(engine).get_table_names()
        assert "users" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="set TRIPSYNC_TEST_PG_URL to run the Postgres migration test")
def test_postgres_head_matches_models():
    schema = f"tripsync_m_{uuid.uuid4().hex[:10]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as connection:
            command.upgrade(_config(connection=connection), "head")
        with engine.connect() as connection:
            assert _diff(connection) == []
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "base")
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
            enum_types = connection.execute(text(
                "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE t.typtype = 'e' AND n.nspname = :schema"
            ), {"schema": schema}).scalars().all()
            assert enum_types == []
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
