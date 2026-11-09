"""Alembic environment for the backend database.

URL resolution (first match wins):
1. `-x url=<sqlalchemy url>` on the command line,
2. sqlalchemy.url set on the Config (tests do this),
3. DATABASE_URL from settings (backend/.env or the environment).

target_metadata is Base.metadata with every model module imported, so
`alembic revision --autogenerate` sees the whole schema. Batch mode is on so
ALTERs also work on SQLite (it recreates tables there; PostgreSQL gets plain
ALTER TABLE statements).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.database import Base, normalize_database_url
from app.models import load_all_models

load_all_models()

config = context.config

# Tests run migrations in-process and must not have their logging reconfigured.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    url = x_args.get("url") or config.get_main_option("sqlalchemy.url")
    if not url:
        from app.core.config import settings

        url = settings.DATABASE_URL
    return normalize_database_url(url)


def _configure_kwargs() -> dict:
    return {
        "target_metadata": target_metadata,
        "render_as_batch": True,
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        # A caller (e.g. a test) handed us an open connection.
        context.configure(connection=connectable, **_configure_kwargs())
        with context.begin_transaction():
            context.run_migrations()
        return

    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _database_url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **_configure_kwargs())
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
