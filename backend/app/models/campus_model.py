# backend/app/models/campus_model.py
"""Campus-scheduling tables (shared-taxi party coordination).

Conventions
- Every datetime column is a NAIVE UTC ``DateTime`` (see app.core.campus_time).
- Enums are Python ``str, Enum`` classes stored as VARCHAR (no native PG enum
  type, no CHECK constraint) so SQLite and PostgreSQL share one schema.
- No migration framework exists: these tables are created by
  ``Base.metadata.create_all`` (run at startup by app.main's lifespan). Existing
  tables are never altered, so a deployed database gets the new tables simply by
  restarting the app.
- Several invariants are enforced by the database itself with portable partial
  unique indexes (``postgresql_where`` + ``sqlite_where``).
"""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import relationship

from app.core import campus_time
from app.db.database import Base


def _now_db() -> datetime:
    """Naive-UTC 'now' via the (monkeypatchable) campus clock."""
    return campus_time.to_db(campus_time.utcnow())


def _enum(py_enum):
    return sa.Enum(py_enum, native_enum=False, create_constraint=False, length=32)


class LandmarkKind(str, enum.Enum):
    CAMPUS_POINT = "CAMPUS_POINT"
    HUB = "HUB"


class TravelMode(str, enum.Enum):
    SHARED_TAXI_PARTY = "SHARED_TAXI_PARTY"


class Direction(str, enum.Enum):
    TO_HUB = "TO_HUB"      # campus point -> hub
    FROM_HUB = "FROM_HUB"  # hub -> campus point


class TravelRequestStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESERVED = "RESERVED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SuggestionReason(str, enum.Enum):
    WINDOW_OVERLAP = "WINDOW_OVERLAP"
    FLEXIBLE_WINDOW = "FLEXIBLE_WINDOW"


class EstimateStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ProposalState(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class PartyState(str, enum.Enum):
    AGREED = "AGREED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"


class ReportOutcome(str, enum.Enum):
    COMPLETED = "COMPLETED"
    DID_NOT_HAPPEN = "DID_NOT_HAPPEN"


class ChangeState(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    SUPERSEDED = "SUPERSEDED"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKED = "ACKED"
    FAILED = "FAILED"


class PartyEventType(str, enum.Enum):
    PARTY_AGREED = "PARTY_AGREED"
    CHANGE_PROPOSED = "CHANGE_PROPOSED"
    CHANGE_REJECTED = "CHANGE_REJECTED"
    PARTY_CHANGED = "PARTY_CHANGED"
    NOTE_UPDATED = "NOTE_UPDATED"
    REPORT_RECORDED = "REPORT_RECORDED"
    PARTY_CANCELLED = "PARTY_CANCELLED"
    PARTY_COMPLETED = "PARTY_COMPLETED"
    PARTY_DISPUTED = "PARTY_DISPUTED"


Column = sa.Column
Integer, String, Boolean, DateTime, Text, JSON = (
    sa.Integer, sa.String, sa.Boolean, sa.DateTime, sa.Text, sa.JSON,
)
FK = sa.ForeignKey


class CampusLandmark(Base):
    __tablename__ = "campus_landmarks"
    __table_args__ = (sa.UniqueConstraint("college_id", "name", name="uq_landmark_college_name"),)

    id = Column(Integer, primary_key=True, index=True)
    college_id = Column(Integer, FK("colleges.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(_enum(LandmarkKind), nullable=False)
    latitude = Column(sa.Float, nullable=False)
    longitude = Column(sa.Float, nullable=False)
    timezone = Column(String, nullable=False, default="Asia/Kolkata")
    active = Column(Boolean, nullable=False, default=True)


class TravelRequest(Base):
    __tablename__ = "travel_requests"
    __table_args__ = (
        sa.Index(
            "ix_travel_requests_corridor",
            "college_id", "origin_landmark_id", "hub_id", "direction", "status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, FK("users.id"), nullable=False, index=True)
    college_id = Column(Integer, FK("colleges.id"), nullable=False)
    mode = Column(_enum(TravelMode), nullable=False, default=TravelMode.SHARED_TAXI_PARTY)
    origin_landmark_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    hub_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    direction = Column(_enum(Direction), nullable=False)
    earliest_departure = Column(DateTime, nullable=False)
    latest_departure = Column(DateTime, nullable=False)
    arrive_by = Column(DateTime, nullable=True)
    timezone = Column(String, nullable=False)
    flexibility_consent = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(_enum(TravelRequestStatus), nullable=False, default=TravelRequestStatus.OPEN)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=_now_db)
    updated_at = Column(DateTime, nullable=False, default=_now_db, onupdate=_now_db)

    user = relationship("User", foreign_keys=[user_id])
    origin_landmark = relationship("CampusLandmark", foreign_keys=[origin_landmark_id])
    hub = relationship("CampusLandmark", foreign_keys=[hub_id])


class PairSuggestion(Base):
    __tablename__ = "pair_suggestions"
    __table_args__ = (
        sa.UniqueConstraint(
            "request_low_id", "request_high_id", "rule_version", name="uq_pair_suggestion"
        ),
        sa.CheckConstraint("request_low_id < request_high_id", name="ck_pair_suggestion_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_low_id = Column(Integer, FK("travel_requests.id"), nullable=False, index=True)
    request_high_id = Column(Integer, FK("travel_requests.id"), nullable=False, index=True)
    rule_version = Column(String, nullable=False)
    reason = Column(_enum(SuggestionReason), nullable=False)
    feasible_start = Column(DateTime, nullable=False)
    feasible_end = Column(DateTime, nullable=False)
    estimate_status = Column(_enum(EstimateStatus), nullable=False)
    estimate_distance_m = Column(Integer, nullable=True)
    estimate_duration_s = Column(Integer, nullable=True)
    estimate_failure = Column(String, nullable=True)  # timeout | unavailable | no_route
    estimate_checked_at = Column(DateTime, nullable=True)
    warnings = Column(JSON, nullable=False, default=list)
    valid_until = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now_db)

    request_low = relationship("TravelRequest", foreign_keys=[request_low_id])
    request_high = relationship("TravelRequest", foreign_keys=[request_high_id])


class CorridorEstimate(Base):
    __tablename__ = "corridor_estimates"
    __table_args__ = (
        sa.UniqueConstraint(
            "origin_landmark_id", "hub_id", "direction", name="uq_corridor_estimate"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    origin_landmark_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    hub_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    direction = Column(_enum(Direction), nullable=False)
    status = Column(_enum(EstimateStatus), nullable=False)
    distance_m = Column(Integer, nullable=True)
    duration_s = Column(Integer, nullable=True)
    failure = Column(String, nullable=True)
    checked_at = Column(DateTime, nullable=False, default=_now_db)


class TravelParty(Base):
    __tablename__ = "travel_parties"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(_enum(PartyState), nullable=False, default=PartyState.AGREED)
    agreed_departure = Column(DateTime, nullable=False)
    meeting_landmark_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    hub_id = Column(Integer, FK("campus_landmarks.id"), nullable=False)
    direction = Column(_enum(Direction), nullable=False)
    timezone = Column(String, nullable=False)
    transport_responsibility = Column(Text, nullable=False)
    cost_note = Column(Text, nullable=True)
    # 0 until the first event; record_party_event increments it, so
    # party.version always equals the latest PartyEvent.version.
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_now_db)
    ended_at = Column(DateTime, nullable=True)
    end_reason = Column(String, nullable=True)

    meeting_landmark = relationship("CampusLandmark", foreign_keys=[meeting_landmark_id])
    hub = relationship("CampusLandmark", foreign_keys=[hub_id])
    members = relationship(
        "PartyMember", back_populates="party", order_by="PartyMember.id"
    )
    events = relationship("PartyEvent", back_populates="party", order_by="PartyEvent.version")


class PartyMember(Base):
    __tablename__ = "party_members"
    __table_args__ = (
        # DB-level "one active party per participant" ...
        sa.Index(
            "uq_active_member_user", "user_id", unique=True,
            postgresql_where=sa.text("active"), sqlite_where=sa.text("active = 1"),
        ),
        # ... and "a request is in at most one active party".
        sa.Index(
            "uq_active_member_request", "request_id", unique=True,
            postgresql_where=sa.text("active"), sqlite_where=sa.text("active = 1"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    party_id = Column(Integer, FK("travel_parties.id"), nullable=False, index=True)
    user_id = Column(Integer, FK("users.id"), nullable=False)
    request_id = Column(Integer, FK("travel_requests.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    report_outcome = Column(_enum(ReportOutcome), nullable=True)
    reported_at = Column(DateTime, nullable=True)

    party = relationship("TravelParty", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
    request = relationship("TravelRequest", foreign_keys=[request_id])


class ConnectionProposal(Base):
    __tablename__ = "connection_proposals"
    __table_args__ = (
        sa.Index(
            "uq_pending_proposal_pair", "pair_low_request_id", "pair_high_request_id",
            unique=True,
            postgresql_where=sa.text("state = 'PENDING'"),
            sqlite_where=sa.text("state = 'PENDING'"),
        ),
        sa.CheckConstraint("pair_low_request_id < pair_high_request_id", name="ck_proposal_pair_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    suggestion_id = Column(Integer, FK("pair_suggestions.id"), nullable=True, index=True)
    proposer_id = Column(Integer, FK("users.id"), nullable=False, index=True)
    recipient_id = Column(Integer, FK("users.id"), nullable=False, index=True)
    proposer_request_id = Column(Integer, FK("travel_requests.id"), nullable=False)
    recipient_request_id = Column(Integer, FK("travel_requests.id"), nullable=False)
    # Filled automatically before insert from the two request ids (see listener below).
    pair_low_request_id = Column(Integer, nullable=False)
    pair_high_request_id = Column(Integer, nullable=False)
    proposer_request_version = Column(Integer, nullable=False)
    recipient_request_version = Column(Integer, nullable=False)
    state = Column(_enum(ProposalState), nullable=False, default=ProposalState.PENDING)
    expires_at = Column(DateTime, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    party_id = Column(Integer, FK("travel_parties.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now_db)
    resolved_at = Column(DateTime, nullable=True)

    suggestion = relationship("PairSuggestion", foreign_keys=[suggestion_id])
    proposer = relationship("User", foreign_keys=[proposer_id])
    recipient = relationship("User", foreign_keys=[recipient_id])
    proposer_request = relationship("TravelRequest", foreign_keys=[proposer_request_id])
    recipient_request = relationship("TravelRequest", foreign_keys=[recipient_request_id])
    party = relationship("TravelParty", foreign_keys=[party_id])


@event.listens_for(ConnectionProposal, "before_insert")
def _fill_proposal_pair(mapper, connection, target):
    if target.pair_low_request_id is None or target.pair_high_request_id is None:
        a, b = target.proposer_request_id, target.recipient_request_id
        target.pair_low_request_id, target.pair_high_request_id = (a, b) if a < b else (b, a)


class PartyEvent(Base):
    __tablename__ = "party_events"
    __table_args__ = (sa.UniqueConstraint("party_id", "version", name="uq_party_event_version"),)

    id = Column(Integer, primary_key=True, index=True)
    party_id = Column(Integer, FK("travel_parties.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    actor_id = Column(Integer, FK("users.id"), nullable=True)
    event_type = Column(String, nullable=False)  # a PartyEventType value
    payload = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime, nullable=False, default=_now_db)

    party = relationship("TravelParty", back_populates="events")


class PartyChangeProposal(Base):
    __tablename__ = "party_change_proposals"
    __table_args__ = (
        sa.Index(
            "uq_pending_change_party", "party_id", unique=True,
            postgresql_where=sa.text("state = 'PENDING'"),
            sqlite_where=sa.text("state = 'PENDING'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    party_id = Column(Integer, FK("travel_parties.id"), nullable=False, index=True)
    proposer_id = Column(Integer, FK("users.id"), nullable=False)
    new_departure = Column(DateTime, nullable=True)
    new_meeting_landmark_id = Column(Integer, FK("campus_landmarks.id"), nullable=True)
    note = Column(Text, nullable=True)
    expected_party_version = Column(Integer, nullable=False)
    state = Column(_enum(ChangeState), nullable=False, default=ChangeState.PENDING)
    created_at = Column(DateTime, nullable=False, default=_now_db)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, FK("users.id"), nullable=True)

    party = relationship("TravelParty", foreign_keys=[party_id])
    new_meeting_landmark = relationship("CampusLandmark", foreign_keys=[new_meeting_landmark_id])


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (sa.Index("ix_outbox_status_next", "status", "next_attempt_at"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, FK("party_events.id"), nullable=False, index=True)
    recipient_id = Column(Integer, FK("users.id"), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(_enum(OutboxStatus), nullable=False, default=OutboxStatus.PENDING)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False, default=_now_db)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now_db)
    sent_at = Column(DateTime, nullable=True)

    event = relationship("PartyEvent", foreign_keys=[event_id])


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "operation", "key", name="uq_idempotency_user_op_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, FK("users.id"), nullable=False)
    operation = Column(String, nullable=False)
    key = Column(String, nullable=False)
    target_id = Column(Integer, nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now_db)
