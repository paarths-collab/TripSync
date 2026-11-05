# backend/app/db/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.core.config import settings  # <-- USES THE CONFIG

_BARE_POSTGRES_PREFIXES = ("postgresql://", "postgres://")


def normalize_database_url(url: str) -> str:
    """Pin bare Postgres URLs to the psycopg2 driver listed in requirements.txt.

    SQLAlchemy 2.x maps a bare ``postgresql://`` to the psycopg (v3) driver, which
    is not installed, and rejects the Heroku-style ``postgres://`` scheme outright.
    """
    for prefix in _BARE_POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


engine = create_engine(
    normalize_database_url(settings.DATABASE_URL),  # <-- READS THE URL FROM SETTINGS
    poolclass=QueuePool,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()