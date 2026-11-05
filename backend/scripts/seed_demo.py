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

Besides the two accounts, seeding also creates (idempotently) two campus
landmarks with fictional coordinates ("Main Gate", a campus point, and "Airport
Terminal", a hub) and one OPEN shared-taxi request per demo rider for the NEXT
day (Asia/Kolkata, relative to seed time): 18:00-19:00 and 18:30-19:30, same
corridor, so the two riders see each other as a suggestion. ``--reset`` removes
the demo riders' campus data (requests, suggestions, proposals, parties and
their events/outbox rows) and leaves every other user's data alone.
"""

import argparse
import os
import sys
from datetime import datetime, time, timedelta

import bcrypt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import campus_time
from app.db import database as app_database
from app.db.database import Base
from app.models import (
    campus_model,
    conversation_model,
    message_model,
    pooling_model,
    profile_model,
    user_model,
)
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

DEMO_TIMEZONE = "Asia/Kolkata"
# Fictional coordinates (deliberately not a real campus or airport).
DEMO_LANDMARKS = (
    {
        "name": "Main Gate",
        "kind": campus_model.LandmarkKind.CAMPUS_POINT,
        "latitude": 12.3400,
        "longitude": 56.7800,
    },
    {
        "name": "Airport Terminal",
        "kind": campus_model.LandmarkKind.HUB,
        "latitude": 12.4100,
        "longitude": 56.8600,
    },
)
# (start, end) local clock times on the day after seeding, one pair per demo user (same order).
DEMO_WINDOWS = ((time(18, 0), time(19, 0)), (time(18, 30), time(19, 30)))


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

    db.flush()
    landmarks = _seed_demo_landmarks(db, college)
    _seed_demo_requests(db, college, users, landmarks)

    db.commit()
    for user in users:
        db.refresh(user)
    return users


def _find_landmark(db: Session, college_id: int, name: str):
    return (
        db.query(campus_model.CampusLandmark)
        .filter(
            campus_model.CampusLandmark.college_id == college_id,
            campus_model.CampusLandmark.name == name,
        )
        .first()
    )


def _seed_demo_landmarks(db: Session, college: user_model.College) -> dict:
    """Get-or-create the demo landmarks; returns {spec name: CampusLandmark}.

    Existing rows are never modified. If a landmark with the wanted name exists
    but has the wrong kind, the demo uses "Demo <name>" instead (created when
    missing, and equally left untouched when present).
    """
    result = {}
    for spec in DEMO_LANDMARKS:
        row = _find_landmark(db, college.id, spec["name"])
        if row is not None and row.kind != spec["kind"]:
            name = f"Demo {spec['name']}"
            row = _find_landmark(db, college.id, name)
            if row is not None and row.kind != spec["kind"]:
                raise ValueError(f"landmark {name!r} exists with an unexpected kind")
        else:
            name = spec["name"]
        if row is None:
            row = campus_model.CampusLandmark(
                college_id=college.id,
                name=name,
                kind=spec["kind"],
                latitude=spec["latitude"],
                longitude=spec["longitude"],
                timezone=DEMO_TIMEZONE,
                active=True,
            )
            db.add(row)
        result[spec["name"]] = row
    db.flush()
    return result


def _demo_window(index: int, now: datetime) -> tuple:
    """(earliest, latest) as naive UTC for demo user ``index``: the next local day."""
    tz = campus_time.parse_tz(DEMO_TIMEZONE)
    tomorrow = now.astimezone(tz).date() + timedelta(days=1)
    start_t, end_t = DEMO_WINDOWS[index]
    earliest = datetime.combine(tomorrow, start_t, tzinfo=tz)
    latest = datetime.combine(tomorrow, end_t, tzinfo=tz)
    return campus_time.to_db(earliest), campus_time.to_db(latest)


def _seed_demo_requests(db: Session, college, users, landmarks: dict) -> None:
    """One OPEN TO_HUB request per demo rider; re-seeding refreshes it instead of adding another."""
    now = campus_time.utcnow()
    now_db = campus_time.to_db(now)
    origin = landmarks["Main Gate"]
    hub = landmarks["Airport Terminal"]
    for index, user in enumerate(users):
        earliest, latest = _demo_window(index, now)
        existing = (
            db.query(campus_model.TravelRequest)
            .filter(
                campus_model.TravelRequest.user_id == user.id,
                campus_model.TravelRequest.origin_landmark_id == origin.id,
                campus_model.TravelRequest.hub_id == hub.id,
                campus_model.TravelRequest.direction == campus_model.Direction.TO_HUB,
                campus_model.TravelRequest.status.in_(
                    (campus_model.TravelRequestStatus.OPEN, campus_model.TravelRequestStatus.RESERVED)
                ),
            )
            .order_by(campus_model.TravelRequest.id)
            .all()
        )
        open_rows = [r for r in existing if r.status == campus_model.TravelRequestStatus.OPEN]
        if any(r.status == campus_model.TravelRequestStatus.RESERVED for r in existing):
            continue  # part of an agreed party: leave it alone
        if open_rows:
            row = open_rows[0]
            if (row.earliest_departure, row.latest_departure) != (earliest, latest):
                row.earliest_departure = earliest
                row.latest_departure = latest
                row.expires_at = latest
                row.version = (row.version or 1) + 1
            row.flexibility_consent = False
            row.arrive_by = None
            for extra in open_rows[1:]:  # defensive: keep exactly one open demo request
                extra.status = campus_model.TravelRequestStatus.CANCELLED
                extra.version = (extra.version or 1) + 1
            continue
        db.add(
            campus_model.TravelRequest(
                user_id=user.id,
                college_id=college.id,
                mode=campus_model.TravelMode.SHARED_TAXI_PARTY,
                origin_landmark_id=origin.id,
                hub_id=hub.id,
                direction=campus_model.Direction.TO_HUB,
                earliest_departure=earliest,
                latest_departure=latest,
                arrive_by=None,
                timezone=DEMO_TIMEZONE,
                flexibility_consent=False,
                expires_at=latest,
                status=campus_model.TravelRequestStatus.OPEN,
                version=1,
                created_at=now_db,
                updated_at=now_db,
            )
        )


def reset_demo(db: Session) -> dict:
    """Delete only data that belongs to the demo users.

    Removes: messages sent by a demo user or inside a conversation a demo user is in,
    those conversations, pooling connections touching a demo user's request, and the
    demo users' pooling requests; and the campus data of the demo riders: their travel
    requests, suggestions and connection proposals touching them, the parties they
    were in (with members, events, outbox rows, change proposals) and their
    idempotency records. Demo users, profiles, landmarks and all other users' rows
    stay; a non-demo participant's request that was RESERVED by a deleted party is
    released like a party cancel (OPEN if still valid, else EXPIRED; version + 1). Returns rows deleted per kind.
    """
    counts = {
        "messages": 0,
        "conversations": 0,
        "pooling_connections": 0,
        "pooling_requests": 0,
        "campus_requests": 0,
        "campus_suggestions": 0,
        "campus_proposals": 0,
        "campus_parties": 0,
        "campus_party_members": 0,
        "campus_events": 0,
        "campus_outbox": 0,
        "campus_idempotency": 0,
    }
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
    _reset_campus(db, demo_ids, counts)
    db.commit()
    return counts


def _reset_campus(db: Session, demo_ids: list[int], counts: dict) -> None:
    """Delete the demo users' campus data in FK-safe order (no commit)."""
    cm = campus_model
    request_ids = [
        row.id
        for row in db.query(cm.TravelRequest.id).filter(cm.TravelRequest.user_id.in_(demo_ids)).all()
    ]
    rid = request_ids or [-1]

    party_ids = {
        row.party_id
        for row in db.query(cm.PartyMember.party_id)
        .filter(or_(cm.PartyMember.user_id.in_(demo_ids), cm.PartyMember.request_id.in_(rid)))
        .all()
    }
    proposals = (
        db.query(cm.ConnectionProposal)
        .filter(
            or_(
                cm.ConnectionProposal.proposer_id.in_(demo_ids),
                cm.ConnectionProposal.recipient_id.in_(demo_ids),
                cm.ConnectionProposal.proposer_request_id.in_(rid),
                cm.ConnectionProposal.recipient_request_id.in_(rid),
            )
        )
        .all()
    )
    party_ids.update(p.party_id for p in proposals if p.party_id is not None)
    pids = sorted(party_ids) or [-1]

    # Release other users' requests that a deleted party was holding.
    released = (
        db.query(cm.TravelRequest)
        .join(cm.PartyMember, cm.PartyMember.request_id == cm.TravelRequest.id)
        .filter(
            cm.PartyMember.party_id.in_(pids),
            cm.TravelRequest.user_id.notin_(demo_ids),
            cm.TravelRequest.status == cm.TravelRequestStatus.RESERVED,
        )
        .all()
    )
    now_db = campus_time.to_db(campus_time.utcnow())
    for row in released:
        # Same rule as party cancel: back to OPEN while still valid, else EXPIRED.
        if row.expires_at > now_db and row.latest_departure > now_db:
            row.status = cm.TravelRequestStatus.OPEN
        else:
            row.status = cm.TravelRequestStatus.EXPIRED
        row.version = (row.version or 1) + 1
    db.flush()

    event_ids = [r.id for r in db.query(cm.PartyEvent.id).filter(cm.PartyEvent.party_id.in_(pids)).all()]
    counts["campus_outbox"] = (
        db.query(cm.OutboxMessage)
        .filter(
            or_(
                cm.OutboxMessage.event_id.in_(event_ids or [-1]),
                cm.OutboxMessage.recipient_id.in_(demo_ids),
            )
        )
        .delete(synchronize_session=False)
    )
    counts["campus_events"] = (
        db.query(cm.PartyEvent)
        .filter(cm.PartyEvent.party_id.in_(pids))
        .delete(synchronize_session=False)
    )
    db.query(cm.PartyChangeProposal).filter(cm.PartyChangeProposal.party_id.in_(pids)).delete(
        synchronize_session=False
    )
    counts["campus_idempotency"] = (
        db.query(cm.IdempotencyRecord)
        .filter(cm.IdempotencyRecord.user_id.in_(demo_ids))
        .delete(synchronize_session=False)
    )
    counts["campus_party_members"] = (
        db.query(cm.PartyMember)
        .filter(cm.PartyMember.party_id.in_(pids))
        .delete(synchronize_session=False)
    )

    proposal_ids = [p.id for p in proposals]
    counts["campus_proposals"] = (
        db.query(cm.ConnectionProposal)
        .filter(cm.ConnectionProposal.id.in_(proposal_ids or [-1]))
        .delete(synchronize_session=False)
    )
    counts["campus_parties"] = (
        db.query(cm.TravelParty).filter(cm.TravelParty.id.in_(pids)).delete(synchronize_session=False)
    )

    suggestion_ids = [
        r.id
        for r in db.query(cm.PairSuggestion.id)
        .filter(or_(cm.PairSuggestion.request_low_id.in_(rid), cm.PairSuggestion.request_high_id.in_(rid)))
        .all()
    ]
    if suggestion_ids:
        # Defensive: unlink anything left (e.g. a non-demo proposal) before deleting.
        db.query(cm.ConnectionProposal).filter(
            cm.ConnectionProposal.suggestion_id.in_(suggestion_ids)
        ).update({cm.ConnectionProposal.suggestion_id: None}, synchronize_session=False)
    counts["campus_suggestions"] = (
        db.query(cm.PairSuggestion)
        .filter(cm.PairSuggestion.id.in_(suggestion_ids or [-1]))
        .delete(synchronize_session=False)
    )
    counts["campus_requests"] = (
        db.query(cm.TravelRequest)
        .filter(cm.TravelRequest.id.in_(rid))
        .delete(synchronize_session=False)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or reset the TripSync demo accounts.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete only the demo users' chat, pooling and campus data (never drops tables)",
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
