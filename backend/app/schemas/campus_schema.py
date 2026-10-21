# backend/app/schemas/campus_schema.py
"""Shared Pydantic v2 schemas for /api/campus.

Request bodies carry offset-aware datetimes (``AwareDatetime``): naive values
fail validation -> 422. Output times use ``TimeOut`` ({utc, local, timezone}).

The ``from_*`` builders turn ORM rows into views. They never include contact
details except ``PartyOut.partner`` phone/email while the party is AGREED, and
they only ever expose what the given ``viewer_id`` is entitled to see.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core import campus_time
from app.models.campus_model import PartyState

IDEMPOTENCY_KEY_MAX = 128


def _val(x: Any) -> Any:
    return getattr(x, "value", x)


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------
class TimeOut(BaseModel):
    """{"utc": "2026-03-01T18:00:00Z", "local": "2026-03-01T23:30:00+05:30", "timezone": "Asia/Kolkata"}"""

    model_config = ConfigDict(frozen=True)

    utc: str
    local: str
    timezone: str

    @classmethod
    def of(cls, dt: Optional[datetime], tz_name: str) -> Optional["TimeOut"]:
        """Build from a DB (naive UTC) or aware datetime; None stays None."""
        if dt is None:
            return None
        aware = campus_time.from_db(dt)
        return cls(
            utc=campus_time.utc_iso(aware),
            local=campus_time.local_iso(aware, tz_name),
            timezone=tz_name,
        )


def time_out(dt: Optional[datetime], tz_name: str) -> Optional[TimeOut]:
    return TimeOut.of(dt, tz_name)


def _check_tz(value: str) -> str:
    campus_time.parse_tz(value)  # ValueError -> 422
    return value


# --------------------------------------------------------------------------
# Small shared views
# --------------------------------------------------------------------------
class LandmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    latitude: float
    longitude: float
    timezone: str

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v):
        return _val(v)


class PlaceOut(BaseModel):
    """Landmark reference embedded in party views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float
    longitude: float


class UserRefOut(BaseModel):
    """Another participant, WITHOUT any contact detail."""

    user_id: int
    full_name: Optional[str] = None


class ConflictDetail(BaseModel):
    """Shape of ``detail`` for 409 responses."""

    code: str
    message: str
    current: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
class TravelRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_landmark_id: int
    hub_id: int
    direction: str
    earliest_departure: AwareDatetime
    latest_departure: AwareDatetime
    arrive_by: Optional[AwareDatetime] = None
    timezone: str
    flexibility_consent: bool = False
    expires_at: Optional[AwareDatetime] = None

    @field_validator("direction")
    @classmethod
    def _direction(cls, v):
        if v not in ("TO_HUB", "FROM_HUB"):
            raise ValueError("direction must be TO_HUB or FROM_HUB")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        return _check_tz(v)


class TravelRequestPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    earliest_departure: Optional[AwareDatetime] = None
    latest_departure: Optional[AwareDatetime] = None
    arrive_by: Optional[AwareDatetime] = None
    flexibility_consent: Optional[bool] = None


class TravelRequestOut(BaseModel):
    id: int
    user_id: int
    college_id: int
    mode: str
    origin_landmark_id: int
    hub_id: int
    direction: str
    earliest_departure: TimeOut
    latest_departure: TimeOut
    arrive_by: Optional[TimeOut] = None
    timezone: str
    flexibility_consent: bool
    expires_at: TimeOut
    status: str
    version: int
    created_at: TimeOut
    updated_at: Optional[TimeOut] = None

    @classmethod
    def from_request(cls, r: Any) -> "TravelRequestOut":
        tz = r.timezone
        return cls(
            id=r.id,
            user_id=r.user_id,
            college_id=r.college_id,
            mode=_val(r.mode),
            origin_landmark_id=r.origin_landmark_id,
            hub_id=r.hub_id,
            direction=_val(r.direction),
            earliest_departure=TimeOut.of(r.earliest_departure, tz),
            latest_departure=TimeOut.of(r.latest_departure, tz),
            arrive_by=TimeOut.of(r.arrive_by, tz),
            timezone=tz,
            flexibility_consent=bool(r.flexibility_consent),
            expires_at=TimeOut.of(r.expires_at, tz),
            status=_val(r.status),
            version=r.version,
            created_at=TimeOut.of(r.created_at, tz),
            updated_at=TimeOut.of(r.updated_at, tz),
        )


# --------------------------------------------------------------------------
# Suggestions
# --------------------------------------------------------------------------
class OtherRequestOut(BaseModel):
    id: int
    earliest_departure: TimeOut
    latest_departure: TimeOut


class FeasibleWindowOut(BaseModel):
    start: TimeOut
    end: TimeOut


class EstimateOut(BaseModel):
    status: str
    distance_m: Optional[int] = None
    duration_s: Optional[int] = None
    failure: Optional[str] = None
    checked_at: Optional[TimeOut] = None


class ProposalRefOut(BaseModel):
    id: int
    state: str
    direction: str  # "outgoing" | "incoming" relative to the viewer


class SuggestionOut(BaseModel):
    id: int
    other: UserRefOut
    other_request: OtherRequestOut
    reason: str
    feasible_window: FeasibleWindowOut
    estimate: EstimateOut
    warnings: List[str] = Field(default_factory=list)
    valid_until: TimeOut
    proposal: Optional[ProposalRefOut] = None

    @classmethod
    def build(
        cls,
        suggestion: Any,
        other_user: Any,
        other_request: Any,
        tz_name: str,
        proposal: Any = None,
        viewer_id: Optional[int] = None,
    ) -> "SuggestionOut":
        """``other_user`` needs id/full_name only; contact fields are never read."""
        ref = None
        if proposal is not None:
            ref = ProposalRefOut(
                id=proposal.id,
                state=_val(proposal.state),
                direction="outgoing" if proposal.proposer_id == viewer_id else "incoming",
            )
        s = suggestion
        return cls(
            id=s.id,
            other=UserRefOut(user_id=other_user.id, full_name=other_user.full_name),
            other_request=OtherRequestOut(
                id=other_request.id,
                earliest_departure=TimeOut.of(other_request.earliest_departure, tz_name),
                latest_departure=TimeOut.of(other_request.latest_departure, tz_name),
            ),
            reason=_val(s.reason),
            feasible_window=FeasibleWindowOut(
                start=TimeOut.of(s.feasible_start, tz_name),
                end=TimeOut.of(s.feasible_end, tz_name),
            ),
            estimate=EstimateOut(
                status=_val(s.estimate_status),
                distance_m=s.estimate_distance_m,
                duration_s=s.estimate_duration_s,
                failure=s.estimate_failure,
                checked_at=TimeOut.of(s.estimate_checked_at, tz_name),
            ),
            warnings=list(s.warnings or []),
            valid_until=TimeOut.of(s.valid_until, tz_name),
            proposal=ref,
        )


class SuggestionsResponse(BaseModel):
    request_id: int
    estimate_status: str
    suggestions: List[SuggestionOut]


# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------
class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledge_warnings: bool = False


class ConnectionAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX)


class ConnectionDecision(BaseModel):
    """Body for decline / withdraw."""

    model_config = ConfigDict(extra="forbid")

    expected_version: Optional[int] = None


class ConnectionOut(BaseModel):
    id: int
    suggestion_id: Optional[int] = None
    state: str
    version: int
    direction: str  # "outgoing" | "incoming" relative to the viewer
    proposer: UserRefOut
    recipient: UserRefOut
    proposer_request_id: int
    recipient_request_id: int
    expires_at: TimeOut
    created_at: TimeOut
    resolved_at: Optional[TimeOut] = None
    party_id: Optional[int] = None

    @classmethod
    def from_proposal(cls, p: Any, viewer_id: int) -> "ConnectionOut":
        tz = p.proposer_request.timezone
        return cls(
            id=p.id,
            suggestion_id=p.suggestion_id,
            state=_val(p.state),
            version=p.version,
            direction="outgoing" if p.proposer_id == viewer_id else "incoming",
            proposer=UserRefOut(user_id=p.proposer_id, full_name=p.proposer.full_name),
            recipient=UserRefOut(user_id=p.recipient_id, full_name=p.recipient.full_name),
            proposer_request_id=p.proposer_request_id,
            recipient_request_id=p.recipient_request_id,
            expires_at=TimeOut.of(p.expires_at, tz),
            created_at=TimeOut.of(p.created_at, tz),
            resolved_at=TimeOut.of(p.resolved_at, tz),
            party_id=p.party_id,
        )


# --------------------------------------------------------------------------
# Parties
# --------------------------------------------------------------------------
class ChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    agreed_departure: Optional[AwareDatetime] = None
    meeting_landmark_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=500)


class ChangeApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_party_version: int


class ChangeReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_party_version: Optional[int] = None


class PartyNotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    cost_note: Optional[str] = Field(default=None, max_length=500)


class PartyCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX)
    reason: Optional[str] = Field(default=None, max_length=200)
    expected_version: Optional[int] = None


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, v):
        if v not in ("COMPLETED", "DID_NOT_HAPPEN"):
            raise ValueError("outcome must be COMPLETED or DID_NOT_HAPPEN")
        return v


class ChangeOut(BaseModel):
    id: int
    party_id: int
    proposer_id: int
    new_departure: Optional[TimeOut] = None
    new_meeting_landmark: Optional[PlaceOut] = None
    note: Optional[str] = None
    expected_party_version: int
    state: str
    created_at: TimeOut
    resolved_at: Optional[TimeOut] = None
    resolved_by: Optional[int] = None

    @classmethod
    def from_change(cls, c: Any, tz_name: Optional[str] = None) -> "ChangeOut":
        tz = tz_name or c.party.timezone
        lm = c.new_meeting_landmark
        return cls(
            id=c.id,
            party_id=c.party_id,
            proposer_id=c.proposer_id,
            new_departure=TimeOut.of(c.new_departure, tz),
            new_meeting_landmark=PlaceOut.model_validate(lm) if lm is not None else None,
            note=c.note,
            expected_party_version=c.expected_party_version,
            state=_val(c.state),
            created_at=TimeOut.of(c.created_at, tz),
            resolved_at=TimeOut.of(c.resolved_at, tz),
            resolved_by=c.resolved_by,
        )


class MemberOut(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    request_id: int
    you: bool
    report_outcome: Optional[str] = None


class PartnerOut(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None


class PartyOut(BaseModel):
    id: int
    state: str
    version: int
    agreed_departure: TimeOut
    meeting_landmark: PlaceOut
    hub: PlaceOut
    direction: str
    transport_responsibility: str
    cost_note: Optional[str] = None
    created_at: TimeOut
    ended_at: Optional[TimeOut] = None
    end_reason: Optional[str] = None
    members: List[MemberOut]
    partner: Optional[PartnerOut] = None
    pending_change: Optional[ChangeOut] = None

    @classmethod
    def from_party(cls, party: Any, viewer_id: int, pending_change: Any = None) -> "PartyOut":
        """Build the viewer's view. The viewer must be a member (callers 404 otherwise).

        Phone/email of the partner are included ONLY while the party is AGREED.
        """
        tz = party.timezone
        members = list(party.members)
        partner_member = next((m for m in members if m.user_id != viewer_id), None)
        partner = None
        if partner_member is not None:
            user = partner_member.user
            agreed = _val(party.state) == PartyState.AGREED.value
            profile = getattr(user, "profile", None)
            partner = PartnerOut(
                user_id=user.id,
                full_name=user.full_name,
                phone_number=(getattr(profile, "phone_number", None) if agreed else None),
                email=(user.email if agreed else None),
            )
        return cls(
            id=party.id,
            state=_val(party.state),
            version=party.version,
            agreed_departure=TimeOut.of(party.agreed_departure, tz),
            meeting_landmark=PlaceOut.model_validate(party.meeting_landmark),
            hub=PlaceOut.model_validate(party.hub),
            direction=_val(party.direction),
            transport_responsibility=party.transport_responsibility,
            cost_note=party.cost_note,
            created_at=TimeOut.of(party.created_at, tz),
            ended_at=TimeOut.of(party.ended_at, tz),
            end_reason=party.end_reason,
            members=[
                MemberOut(
                    user_id=m.user_id,
                    full_name=m.user.full_name,
                    request_id=m.request_id,
                    you=(m.user_id == viewer_id),
                    report_outcome=_val(m.report_outcome) if m.report_outcome else None,
                )
                for m in members
            ],
            partner=partner,
            pending_change=(
                ChangeOut.from_change(pending_change, tz) if pending_change is not None else None
            ),
        )


class ActivePartyResponse(BaseModel):
    party: Optional[PartyOut] = None
    recently_ended: Optional[PartyOut] = None
    latest_version: Optional[int] = None
    server_time: str


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------
class EventOut(BaseModel):
    version: int
    event_type: str
    actor_id: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: str  # UTC ISO-8601 with trailing Z

    @classmethod
    def from_event(cls, e: Any) -> "EventOut":
        return cls(
            version=e.version,
            event_type=e.event_type,
            actor_id=e.actor_id,
            payload=dict(e.payload or {}),
            occurred_at=campus_time.utc_iso(e.occurred_at),
        )


class EventsResponse(BaseModel):
    party_id: Optional[int] = None
    events: List[EventOut] = Field(default_factory=list)
    latest_version: Optional[int] = None
    party: Optional[PartyOut] = None
    server_time: Optional[str] = None
