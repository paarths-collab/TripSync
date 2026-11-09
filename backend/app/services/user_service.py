# backend/app/services/user_service.py

import re
from datetime import date, datetime, timezone
from typing import Optional

import bcrypt
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import user_model
from app.services.college_service import (  # noqa: F401  (re-exported for older imports)
    ALLOWED_COLLEGES,
    accepts_email,
    canonical_college_name,
    get_or_create_college,
)

MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_BYTES = 72  # bcrypt ignores everything after 72 bytes
MINIMUM_AGE_YEARS = 18
_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A real bcrypt hash of a random value: checking a password against it costs the
# same as a real check, so unknown emails do not answer measurably faster.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser-not-a-password", bcrypt.gensalt()).decode("utf-8")


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """The server's current date (monkeypatched in tests)."""
    return date.today()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a plain text password matches a hashed password."""
    encoded = plain_password.encode('utf-8')
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode('utf-8'))
    except ValueError:
        return False


def burn_password_check(plain_password: str) -> None:
    """Spend the time of one bcrypt check (used when there is no user to check against)."""
    verify_password(plain_password, _DUMMY_HASH)


def validate_new_password(password: str) -> None:
    """422 weak_password unless 8+ characters and at most 72 UTF-8 bytes."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_CHARS:
        raise api_error(422, "weak_password", f"Password must be at least {MIN_PASSWORD_CHARS} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise api_error(422, "weak_password", f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")


def parse_date_of_birth(value: Optional[str]) -> date:
    """'YYYY-MM-DD' -> date; 422 invalid_date_of_birth / underage otherwise."""
    if not isinstance(value, str) or not _DOB_RE.match(value.strip()):
        raise api_error(422, "invalid_date_of_birth", "Date of birth must be a date in YYYY-MM-DD format.")
    try:
        dob = date.fromisoformat(value.strip())
    except ValueError:
        raise api_error(422, "invalid_date_of_birth", "Date of birth is not a valid date.") from None
    current = today()
    if dob > current or dob.year < 1900:
        raise api_error(422, "invalid_date_of_birth", "Date of birth is not a valid date.")
    if age_on(dob, current) < MINIMUM_AGE_YEARS:
        raise api_error(422, "underage", f"You must be at least {MINIMUM_AGE_YEARS} years old to register.")
    return dob


def age_on(dob: date, on: date) -> int:
    """Completed years; someone born on 29 February turns a year older on 1 March in common years."""
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def get_user_by_email(db: Session, email: str):
    """Fetch a user by email, case-insensitively (emails are stored lowercase)."""
    normalized = normalize_email(email)
    if not normalized:
        return None
    user = db.query(user_model.User).filter(user_model.User.email == normalized).first()
    if user is not None:
        return user
    # Rows written before emails were normalised may still contain capitals.
    return (
        db.query(user_model.User)
        .filter(func.lower(user_model.User.email) == normalized)
        .order_by(user_model.User.id)
        .first()
    )


def get_user_by_id(db: Session, user_id: int):
    return db.get(user_model.User, user_id)


def resolve_college(db: Session, college_id: Optional[int], college_name: Optional[str]) -> user_model.College:
    if college_id is not None:
        college = db.get(user_model.College, college_id)
        if college is None:
            raise api_error(422, "invalid_college", "Unknown college.")
        return college
    name = canonical_college_name(college_name)
    if name is None:
        raise api_error(422, "invalid_college", "Choose a college from the list.")
    return get_or_create_college(db, college_name=name)


def register_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    college_id: Optional[int],
    college_name: Optional[str],
    date_of_birth: Optional[str],
) -> user_model.User:
    """Validate and create an unverified account. Raises coded HTTP errors."""
    email = normalize_email(email)
    college = resolve_college(db, college_id, college_name)
    if not college.email_domains:
        raise api_error(422, "email_domain_mismatch", "Registration is not open for this college yet.")
    if not accepts_email(college, email):
        domains = ", ".join(college.email_domains)
        raise api_error(422, "email_domain_mismatch", f"Use your college email address ({domains}).")
    dob = parse_date_of_birth(date_of_birth)
    validate_new_password(password)
    if get_user_by_email(db, email) is not None:
        raise api_error(409, "email_taken", "An account with this email already exists.")

    user = user_model.User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        college_id=college.id,
        date_of_birth=dob,
        email_verified_at=None,
        token_version=0,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise api_error(409, "email_taken", "An account with this email already exists.") from None
    db.refresh(user)
    return user
