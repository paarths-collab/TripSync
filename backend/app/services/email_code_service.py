# backend/app/services/email_code_service.py
"""Issue and check one-time 6-digit email codes.

- Codes are stored as HMAC-SHA256(JWT_SECRET_KEY, "<purpose>:<email>:<code>").
- A code lives CODE_TTL_SECONDS (10 minutes). After MAX_ATTEMPTS (5) wrong
  guesses it is dead and every further try answers code_expired.
- Issuing a new code retires the user's earlier unused codes of that purpose.
- One code email per address and purpose per RESEND_COOLDOWN_SECONDS (60 s),
  tracked in memory for every address (registered or not) so the cooldown
  itself does not reveal which addresses have accounts.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import api_error
from app.core.rate_limit import email_cooldown
from app.models import user_model
from app.models.email_code_model import EmailCode, EmailCodePurpose

CODE_TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
CODE_DIGITS = 6


def utcnow() -> datetime:
    """Naive UTC now (monkeypatched in tests)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_code(purpose: str, email: str, code: str) -> str:
    message = f"{purpose}:{email}:{code}".encode("utf-8")
    return hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def _cooldown_key(purpose: str, email: str) -> str:
    return f"{purpose}:{email}"


def cooldown_remaining(purpose: str, email: str) -> float:
    return email_cooldown.remaining(_cooldown_key(purpose, email))


def try_start_cooldown(purpose: str, email: str) -> float:
    """Start the resend cooldown if none is running; returns seconds left otherwise (0 = started)."""
    return email_cooldown.try_start(_cooldown_key(purpose, email), RESEND_COOLDOWN_SECONDS)


def start_cooldown(purpose: str, email: str) -> None:
    email_cooldown.start(_cooldown_key(purpose, email), RESEND_COOLDOWN_SECONDS)


def issue_code(db: Session, user: user_model.User, purpose: EmailCodePurpose) -> str:
    """Create a fresh code for ``user`` (retiring older ones) and COMMIT. Returns the plain code."""
    now = utcnow()
    db.execute(
        update(EmailCode)
        .where(
            EmailCode.user_id == user.id,
            EmailCode.purpose == purpose.value,
            EmailCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    code = generate_code()
    db.add(EmailCode(
        user_id=user.id,
        email=user.email,
        purpose=purpose.value,
        code_hash=hash_code(purpose.value, user.email, code),
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        attempts=0,
        created_at=now,
    ))
    db.commit()
    return code


def _invalid_code():
    return api_error(400, "invalid_code", "That code is not correct.")


def _expired_code():
    return api_error(400, "code_expired", "That code has expired. Request a new one.")


def consume_code(db: Session, user: user_model.User | None, purpose: EmailCodePurpose, code: str) -> user_model.User:
    """Check ``code`` for ``user`` and mark it used (flushed, not committed).

    Raises 400 invalid_code (wrong code, no live code, unknown or inactive user)
    or 400 code_expired (past its lifetime, or out of attempts). A wrong guess is
    counted and committed before raising.
    """
    if user is None or not user.is_active:
        raise _invalid_code()
    row = (
        db.query(EmailCode)
        .filter(
            EmailCode.user_id == user.id,
            EmailCode.purpose == purpose.value,
            EmailCode.consumed_at.is_(None),
        )
        .order_by(EmailCode.id.desc())
        .first()
    )
    if row is None:
        raise _invalid_code()
    now = utcnow()
    if row.expires_at <= now or row.attempts >= MAX_ATTEMPTS:
        raise _expired_code()

    code = (code or "").strip()
    if not (len(code) == CODE_DIGITS and code.isascii() and code.isdigit()):
        raise _invalid_code()  # not a guess at a real code: not counted
    if not hmac.compare_digest(row.code_hash, hash_code(purpose.value, row.email, code)):
        # Atomic increment so concurrent guesses cannot share one attempt.
        db.execute(
            update(EmailCode)
            .where(EmailCode.id == row.id, EmailCode.attempts < MAX_ATTEMPTS)
            .values(attempts=EmailCode.attempts + 1)
        )
        db.commit()
        raise _invalid_code()

    # Single use even under concurrency: only one request can flip consumed_at.
    result = db.execute(
        update(EmailCode)
        .where(EmailCode.id == row.id, EmailCode.consumed_at.is_(None), EmailCode.attempts < MAX_ATTEMPTS)
        .values(consumed_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise _invalid_code()
    return user
