# backend/scripts/seed_demo.py

"""Seed or reset synthetic demo accounts for TripSync.

The two accounts are demonstration participants with fictional data: made-up
names, example.test emails and 1000000000x phone numbers. They are not real
people.

Run from backend/:

    DEMO_PASSWORD=... python -m scripts.seed_demo           # seed (idempotent)
    DEMO_PASSWORD=... python -m scripts.seed_demo --reset   # delete demo data only

The password is read only from the DEMO_PASSWORD environment variable and is
never printed or logged. Nothing here drops tables.
"""

import argparse
import os
import sys

import bcrypt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import database as app_database
from app.db.database import Base
from app.models import conversation_model, message_model, pooling_model, profile_model, user_model
from app.services.user_service import ALLOWED_COLLEGES, get_or_create_college, verify_password

DEMO_COLLEGE_NAME = "DJSCE"
assert DEMO_COLLEGE_NAME in ALLOWED_COLLEGES

MIN_PASSWORD_LENGTH = 8

DEMO_USERS = (
    {
        "email": "demo-rider-a@example.test",
        "full_name": "Demo Rider A (demo)",
        "phone": "+10000000001",
    },
    {
        "email": "demo-rider-b@example.test",
        "full_name": "Demo Rider B (demo)",
        "phone": "+10000000002",
    },
)
DEMO_EMAILS = tuple(spec["email"] for spec in DEMO_USERS)


def _hash_password(password: str) -> str:
    # Same call as user_service.create_user.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _demo_user_ids(db: Session) -> list[int]:
    rows = db.query(user_model.User.id).filter(user_model.User.email.in_(DEMO_EMAILS)).all()
    return [row.id for row in rows]


def seed_demo(db: Session, password: str) -> list[user_model.User]:
    """Create or update the college and the two demo users. Safe to run repeatedly."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"demo password must be at least {MIN_PASSWORD_LENGTH} characters")

    college = get_or_create_college(db, college_name=DEMO_COLLEGE_NAME)

    users: list[user_model.User] = []
    for spec in DEMO_USERS:
        user = db.query(user_model.User).filter(user_model.User.email == spec["email"]).first()
        if user is None:
            user = user_model.User(email=spec["email"], hashed_password=_hash_password(password))
            db.add(user)
            db.flush()  # assigns user.id for the profile row
        elif not verify_password(password, user.hashed_password):
            user.hashed_password = _hash_password(password)
        user.full_name = spec["full_name"]
        user.college_id = college.id

        profile = db.query(profile_model.Profile).filter(profile_model.Profile.user_id == user.id).first()
        if profile is None:
            profile = profile_model.Profile(user_id=user.id)
            db.add(profile)
        profile.phone_number = spec["phone"]
        users.append(user)

    db.commit()
    for user in users:
        db.refresh(user)
    return users


def reset_demo(db: Session) -> dict:
    """Delete only data that belongs to the demo users.

    Removes: messages sent by a demo user or inside a conversation a demo user is in,
    those conversations, pooling connections touching a demo user's request, and the
    demo users' pooling requests. Demo users, profiles and all other users' rows stay.
    Returns the number of rows deleted per kind.
    """
    counts = {"messages": 0, "conversations": 0, "pooling_connections": 0, "pooling_requests": 0}
    demo_ids = _demo_user_ids(db)
    if not demo_ids:
        return counts

    request_ids = [
        row.id
        for row in db.query(pooling_model.PoolingRequest.id)
        .filter(pooling_model.PoolingRequest.user_id.in_(demo_ids))
        .all()
    ]
    conversation_ids = [
        row.id
        for row in db.query(conversation_model.Conversation.id)
        .filter(
            or_(
                conversation_model.Conversation.user1_id.in_(demo_ids),
                conversation_model.Conversation.user2_id.in_(demo_ids),
            )
        )
        .all()
    ]

    counts["messages"] = (
        db.query(message_model.Message)
        .filter(
            or_(
                message_model.Message.sender_id.in_(demo_ids),
                message_model.Message.conversation_id.in_(conversation_ids),
            )
        )
        .delete(synchronize_session=False)
    )
    counts["conversations"] = (
        db.query(conversation_model.Conversation)
        .filter(conversation_model.Conversation.id.in_(conversation_ids))
        .delete(synchronize_session=False)
    )
    counts["pooling_connections"] = (
        db.query(pooling_model.PoolingConnection)
        .filter(
            or_(
                pooling_model.PoolingConnection.sender_request_id.in_(request_ids),
                pooling_model.PoolingConnection.receiver_request_id.in_(request_ids),
            )
        )
        .delete(synchronize_session=False)
    )
    counts["pooling_requests"] = (
        db.query(pooling_model.PoolingRequest)
        .filter(pooling_model.PoolingRequest.user_id.in_(demo_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or reset the TripSync demo accounts.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete only the demo users' chat and pooling data (never drops tables)",
    )
    args = parser.parse_args(argv)

    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"error: set DEMO_PASSWORD to a demo password of at least {MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        sys.exit(1)

    Base.metadata.create_all(bind=app_database.engine)
    db = app_database.SessionLocal()
    try:
        if args.reset:
            counts = reset_demo(db)
            summary = ", ".join(f"{name}={count}" for name, count in counts.items())
            print(f"Demo reset complete. Rows deleted: {summary}")
        else:
            users = seed_demo(db, password)
            emails = ", ".join(user.email for user in users)
            print(f"Demo seed complete: {len(users)} demo accounts ({emails}) in college {DEMO_COLLEGE_NAME}.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
