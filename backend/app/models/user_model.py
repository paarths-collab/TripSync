# backend/app/models/user_model.py

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class College(Base):
    __tablename__ = "colleges"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    # Lowercase email domains accepted at registration; empty = registration closed.
    email_domains = Column(JSON, nullable=False, default=list, server_default=sa.text("'[]'"))
    users = relationship("User", back_populates="college")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Stored lowercase and trimmed (see user_service.normalize_email).
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    college_id = Column(Integer, ForeignKey("colleges.id"))
    # Nullable only for accounts created before date of birth was collected.
    date_of_birth = Column(Date, nullable=True)
    # NULL until the address is confirmed with an emailed code; login requires it.
    email_verified_at = Column(DateTime, nullable=True)
    # Embedded in every JWT as "tv"; bumping it revokes all existing tokens.
    token_version = Column(Integer, nullable=False, default=0, server_default=sa.text("0"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=sa.true())

    college = relationship("College", back_populates="users")
    created_at = Column(DateTime, default=datetime.utcnow)

    # One-to-one link to the user's Profile.
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None
