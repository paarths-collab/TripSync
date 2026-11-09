#!/usr/bin/env python3
"""
Script to reset the database by dropping all tables and recreating them.
WARNING: This will delete all data in the database!

Intended for local development databases. Production databases are managed
with Alembic (`alembic upgrade head`); after a reset of a database that Alembic
manages, run `alembic stamp head` so the migration history matches.
"""

from app.db.database import Base, engine
from app.models import load_all_models  # registers every table, campus models included

load_all_models()


def reset_database():
    """Drop all tables and recreate them."""
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)

    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)

    print("Database reset complete.")
    print("All tables have been recreated with the new schema.")

if __name__ == "__main__":
    reset_database()
