# backend/app/models/email_code_model.py
"""One-time 6-digit codes sent by email (address verification, password reset).

Only an HMAC of the code is stored (see app.services.email_code_service). All
datetimes are naive UTC.
"""

import enum
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.db.database import Base


class EmailCodePurpose(str, enum.Enum):
    VERIFY = "VERIFY"
    RESET = "RESET"


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmailCode(Base):
    __tablename__ = "email_codes"
    __table_args__ = (sa.Index("ix_email_codes_user_purpose", "user_id", "purpose"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The address the code was sent to; part of the HMAC input.
    email = Column(String, nullable=False)
    purpose = Column(String(16), nullable=False)  # an EmailCodePurpose value
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default=sa.text("0"))
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
