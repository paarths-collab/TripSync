# backend/app/db/schema.py
"""Startup schema handling.

Production (PostgreSQL) schemas are managed by Alembic: run
``alembic upgrade head`` from backend/ before starting the app.

For local SQLite development (DB_AUTO_CREATE, on by default for SQLite URLs)
the app creates missing tables itself with ``Base.metadata.create_all``. When
it creates the schema in an EMPTY database it also stamps the Alembic head, so
later ``alembic upgrade head`` runs apply only newer migrations. create_all
never alters existing tables: an older local database needs Alembic (or a reset).
"""

import logging
import os

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.database import Base
from app.models import load_all_models

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALEMBIC_INI = os.path.join(BACKEND_DIR, "alembic.ini")
MIGRATIONS_DIR = os.path.join(BACKEND_DIR, "migrations")


def alembic_config() -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("script_location", MIGRATIONS_DIR)
    return config


def alembic_head() -> str | None:
    """The head revision of backend/migrations."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def auto_create_schema(engine: Engine) -> None:
    """create_all for development; stamps the Alembic head when the database was empty."""
    load_all_models()
    existing = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)
    if existing:
        if "alembic_version" not in existing:
            logger.warning(
                "Database tables were not created by Alembic; create_all does not add new "
                "columns to existing tables. See README (Migrations) if startup errors follow."
            )
        return
    script = ScriptDirectory.from_config(alembic_config())
    head = script.get_current_head()
    with engine.begin() as connection:
        MigrationContext.configure(connection).stamp(script, head)
    logger.info("Created a fresh schema and stamped Alembic revision %s", head)
