# Campus scheduling (shared-taxi parties)

This document describes the campus-scheduling API in the TripSync backend, as implemented on branch `repair/backend-logic`. All endpoints live under `/api/campus`. Source files are in `backend/app/`. Every statement here was checked against that code.

Contents

1. What it is and is not
2. Concepts and state machines
3. Eligibility rule and constants
4. Endpoints
5. Reconciliation for clients
6. Concurrency design
7. Compatibility and migration
8. Limitations, non-goals and open decisions
9. Acceptance cases

---

## 1. What it is and is not

Two students who share a campus meeting point and a hub can agree to share one taxi between them. The flow:

1. Each student creates a travel request: a departure window, a corridor (campus point to hub, or hub to campus point) and a direction.
2. The student's client asks for suggestions. The server returns other compatible requests whose departure windows overlap.
3. One student sends a connection proposal for a suggestion. The other student accepts or declines.
4. Accepting creates a **travel party** (an agreement between the two members) and reserves both requests.
5. Members may propose a change of time or meeting point, and report afterwards whether the trip happened.

It is **not**:

- A booking, a payment, a dispatch, or a safety guarantee. Participants arrange and pay for the taxi themselves. Each party carries this text: `"Participants arrange and pay for the taxi themselves. This agreement is not a booking, dispatch or safety guarantee."` (`TRANSPORT_RESPONSIBILITY_TEXT`).
- A driver or dispatch system. The data model and the API have no driver role.
- A payment system. `cost_note` is free text that members may edit. No code path moves money.
- A live-location feature. The server stores no client coordinates. The only coordinates are the fixed landmark coordinates.
- A verified-completion system. Completion is self-reported (see section 5).
- An identity check. A request copies `college_id` from the user's account when it is created. Matching only happens between users with the same `college_id`. This limits who can see whom. It does not verify student status. The API does not check age; "adult students" is a product assumption that the code does not enforce.

---

## 2. Concepts and state machines

Tables (names as created by SQLAlchemy in `backend/app/models/campus_model.py`):

| Concept | Table | Notes |
|---|---|---|
| Campus point and hub | `campus_landmarks` | Per college. Unique `(college_id, name)`. `kind` is `CAMPUS_POINT` or `HUB`. |
| Travel request | `travel_requests` | One row per request. Has `version`. |
| Pair suggestion | `pair_suggestions` | Derived information about a pair of requests. No reservation. |
| Corridor estimate cache | `corridor_estimates` | One row per `(origin, hub, direction)`. |
| Connection proposal | `connection_proposals` | Has `version`. |
| Travel party | `travel_parties` | Has `version`, which equals the latest event version. |
| Party member | `party_members` | One row per member. `active` flag. |
| Party change proposal | `party_change_proposals` | Time or meeting-point change awaiting approval. |
| Party event | `party_events` | Append-only log per party, ordered by `version`. |
| Outbox message | `outbox_messages` | One row per event per member, for socket delivery. |
| Idempotency record | `idempotency_records` | Stored result of a successful accept or cancel. |

Enum columns are stored as `VARCHAR(32)` with no native enum type and no `CHECK` constraint. The application enforces the allowed values.

### 2.1 TravelRequest

```
OPEN ----accept----------------------> RESERVED ----party COMPLETED-------> FULFILLED
 |                                       |
 |--owner DELETE---------> CANCELLED     |--party ended, see transitions below
 |
 +--expires_at reached (lazy)---> EXPIRED
```

| From | To | Trigger |
|---|---|---|
| OPEN | RESERVED | A connection proposal is accepted. Both requests move. |
| OPEN | CANCELLED | Owner `DELETE /requests/{id}`. |
| OPEN | EXPIRED | `expires_at` has passed. Set lazily by the expiry sweep (`expire_stale`), which runs on the request list, read, create, edit and cancel calls and on the suggestions call. |
| RESERVED | FULFILLED | Party reaches COMPLETED. |
| RESERVED | CANCELLED | Party is cancelled by a member, for the canceller's own request. Also both members' requests when the party is DISPUTED or ends `did_not_happen`. |
| RESERVED | OPEN | Party is cancelled by a member, for the other member's request, if that request still has `expires_at` and `latest_departure` in the future. It is not re-matched automatically. |
| RESERVED | EXPIRED | Party is cancelled, for the other member's request, if `expires_at` or `latest_departure` has passed. |

Every status change increments `version`. FULFILLED, CANCELLED and EXPIRED are terminal. A RESERVED request leaves that state only through the party transitions above.

### 2.2 PairSuggestion

A suggestion has no status. It is a row keyed by `(request_low_id, request_high_id, rule_version)` with `low < high`, enforced by a check constraint.

- Creating or refreshing suggestions never changes any request's status or version, and never removes a request from anyone else's search.
- `valid_until` is set to now plus `SUGGESTION_TTL_MINUTES`. It is informational. `POST /suggestions/{id}/connections` does not check it; eligibility is re-evaluated at that time.
- A suggestion row is deleted when a PATCH actually changes either of its requests, or when either request is cancelled while OPEN. The pending proposals on the request are expired in the same transaction.
- Suggestions are recomputed on each `GET /requests/{id}/suggestions`. The stored rows are the anchor that a connection proposal points to.

### 2.3 ConnectionProposal

```
PENDING --recipient accepts--> ACCEPTED   (a TravelParty is created)
   |
   |--recipient declines----> DECLINED
   |--proposer withdraws----> WITHDRAWN
   +--expires_at passes, a request is edited or cancelled,
      a competing proposal is accepted, or a request expires--> EXPIRED
```

- `expires_at` is `min(now + PROPOSAL_TTL_MINUTES, earlier of the two latest_departure values)`.
- Each proposal stores the `version` of both requests at creation. Accept checks them.
- Each transition increments `version` (the value the client sends as `expected_version`).
- A partial unique index allows at most one PENDING proposal per request pair.
- Proposals stay in the table as history. Only their `suggestion_id` link is cleared when the suggestion row is deleted.

### 2.4 TravelParty

```
AGREED --member cancels-------------------> CANCELLED   (end_reason cancelled_by_member)
AGREED --both report DID_NOT_HAPPEN-------> CANCELLED   (end_reason did_not_happen)
AGREED --both report COMPLETED------------> COMPLETED   (end_reason completed)
AGREED --reports disagree-----------------> DISPUTED    (end_reason disputed)
```

- A party is created in AGREED. Its members are created `active = true`. Ending the party sets every member `active = false`.
- `agreed_departure` is the earliest feasible instant (see section 3), not the end of the window.
- `timezone` comes from the meeting landmark. It controls how times are rendered as `local`. Eligibility uses absolute instants.
- Terminal states cannot be reopened.

### 2.5 PartyChangeProposal

```
PENDING --other member approves----> APPROVED    (party values change, party.version + 1)
   |--other member rejects---------> REJECTED
   |--proposer withdraws-----------> WITHDRAWN
   +--party ends---------------------> SUPERSEDED
```

- At most one PENDING change per party (partial unique index `uq_pending_change_party`).
- The proposer's approval is implicit. The proposer cannot approve or reject their own change.
- The party's values do not change until approval.

### 2.6 PartyMember, PartyEvent, OutboxMessage, IdempotencyRecord

- **PartyMember**: `active` is true while the party is AGREED. `report_outcome` (`COMPLETED` or `DID_NOT_HAPPEN`) and `reported_at` are set when the member reports.
- **PartyEvent**: unique `(party_id, version)`. The first event (PARTY_AGREED) has version 1. Event types: `PARTY_AGREED`, `CHANGE_PROPOSED`, `CHANGE_REJECTED`, `PARTY_CHANGED`, `NOTE_UPDATED`, `REPORT_RECORDED`, `PARTY_CANCELLED`, `PARTY_COMPLETED`, `PARTY_DISPUTED`.
- **OutboxMessage**: one row per event per member (both members, including the actor). Status flow in section 5.4.
- **IdempotencyRecord**: unique `(user_id, operation, key)`. Operations are `accept_connection` and `cancel_party`. Stores only 2xx responses.

### 2.7 Database-level invariants

These are enforced by the database, not only by application code.

| Object | Table | Enforces |
|---|---|---|
| `uq_active_member_user` (partial, `WHERE active`) | `party_members` | A user is an active member of at most one party. |
| `uq_active_member_request` (partial, `WHERE active`) | `party_members` | A request belongs to at most one active party. |
| `uq_pending_proposal_pair` (partial, `WHERE state = 'PENDING'`) | `connection_proposals` | At most one PENDING proposal per request pair. |
| `uq_pending_change_party` (partial, `WHERE state = 'PENDING'`) | `party_change_proposals` | At most one PENDING change per party. |
| `uq_party_event_version` | `party_events` | Event versions are unique within a party. |
| `uq_idempotency_user_op_key` | `idempotency_records` | One stored result per user, operation and key. |
| `uq_pair_suggestion` | `pair_suggestions` | One suggestion per pair and rule version. |
| `ck_pair_suggestion_order`, `ck_proposal_pair_order` | `pair_suggestions`, `connection_proposals` | `request_low_id < request_high_id`. |
| `uq_landmark_college_name` | `campus_landmarks` | Landmark names are unique per college. |
| `uq_corridor_estimate` | `corridor_estimates` | One estimate per corridor and direction. |

The partial indexes use `WHERE active` on PostgreSQL and `WHERE active = 1` on SQLite. The application checks for overlapping requests and for the open-request limit (section 3, and section 4). Neither is a database constraint. Both run under a lock on the user row.

---

## 3. Eligibility rule and constants

### 3.1 Eligibility

Eligibility is decided by `campus_rules.eligible_pair` (`backend/app/core/campus_rules.py`) using the rule version `window-overlap-v1`. It runs when suggestions are requested and again when a connection is proposed or accepted. It is not stored.

The creation time of a request is never read.

Checks run in this order. The first failure wins:

1. `different_user`: same user.
2. `different_college`: `college_id` differs.
3. `different_corridor`: `mode`, `origin_landmark_id` or `hub_id` differs.
4. `opposite_direction`: `TO_HUB` against `FROM_HUB`.
5. `not_open`: either request is not OPEN.
6. `expired`: either request has `expires_at <= now` or `latest_departure <= now`.
7. `disjoint_windows`: no overlap, even with flexibility.

Overlap is inclusive. Two windows `[a_start, a_end]` and `[b_start, b_end]` overlap when `max(starts) <= min(ends)`. Touching windows overlap at one instant: `[0, 3]` and `[3, 5]` give `(3, 3)`. Windows one second apart do not overlap.

- `WINDOW_OVERLAP`: the windows overlap. The feasible window is the intersection.
- `FLEXIBLE_WINDOW`: the windows do not overlap, but both requests have `flexibility_consent = true` and the windows, each widened by `FLEX_MINUTES` on both sides, overlap. The feasible window is the intersection of the widened windows, so it can extend up to `FLEX_MINUTES` beyond a user's own window. One-sided consent is not enough.

Candidate lookup is an indexed query on `(college, origin, hub, direction)` with `status = OPEN`, `latest_departure > now` and `expires_at > now`, bounded by the window plus `2 * FLEX_MINUTES`. It returns at most `MAX_CANDIDATES` (200) candidates, nearest to the caller's window midpoint. When there are more, the response sets `truncated: true`.

A party departs at `max(feasible_start, now rounded up to the minute)`. The agreement is rejected with `window_closed` if that instant is after `feasible_end`.

### 3.2 Warnings

When a request has `arrive_by`, the suggestion carries a warning:

- `cannot_meet_arrive_by`: the estimate is VERIFIED and the earliest feasible departure plus the estimated duration is after the earliest `arrive_by`.
- `deadline_unverified`: the estimate is UNVERIFIED.

Proposing a connection on a suggestion with warnings requires `acknowledge_warnings: true`. Otherwise the response is 409 `warnings_unacknowledged`.

### 3.3 Constants

From `backend/app/core/campus_rules.py`:

| Constant | Value | Meaning |
|---|---|---|
| `RULE_VERSION` | `"window-overlap-v1"` | Stored on each suggestion. |
| `MAX_WINDOW_HOURS` | 6 | Longest allowed departure window. |
| `MAX_LEAD_DAYS` | 14 | Earliest departure may be at most this far ahead. Also the limit for a proposed change. |
| `MIN_WINDOW_MINUTES` | 10 | Shortest allowed departure window. |
| `FLEX_MINUTES` | 30 | Widening on each side for `FLEXIBLE_WINDOW`. |
| `MAX_OPEN_REQUESTS_PER_USER` | 3 | Counts requests in OPEN or RESERVED. |
| `PROPOSAL_TTL_MINUTES` | 30 | Proposal lifetime, capped by the earlier `latest_departure`. |
| `SUGGESTION_TTL_MINUTES` | 15 | `valid_until` of a suggestion. Informational. |
| `RECENT_ENDED_HOURS` | 24 | How long `recently_ended` is returned by `GET /parties/active`. |
| `ESTIMATE_TTL_MINUTES` | 360 | A VERIFIED corridor estimate is reused for this long. |
| `ESTIMATE_RETRY_SECONDS` | 60 | An UNVERIFIED estimate is not retried for this long. |
| `OUTBOX_MAX_ATTEMPTS` | 8 | Failed deliveries before a row becomes FAILED. |
| `OUTBOX_BACKOFF_BASE_SECONDS` | 5 | Retry delay base. |
| `OUTBOX_BACKOFF_MAX_SECONDS` | 300 | Retry delay cap. |
| `REQUEST_EXPIRY_GRACE_HOURS` | 1 | `expires_at` may be at most `latest_departure` plus this. |

Other values that affect behavior, defined in the module named:

| Value | Where | Meaning |
|---|---|---|
| `MAX_CANDIDATES = 200` | `campus_suggestion_service.py` | Candidates examined per suggestions call. |
| `VALID_UNTIL_REFRESH = 60 s` | `campus_suggestion_service.py` | `valid_until` is rewritten only when it moves forward by this much. |
| `PROVIDER_CALL_TIMEOUT_SECONDS = 8.0` | `campus_estimates.py` | Hard ceiling for one routing-provider call. |
| `CLAIM_LEASE_SECONDS = 30` | `campus_outbox.py` | Lease on an outbox row while a dispatcher holds it. |
| `OUTBOX_SEND_TIMEOUT_SECONDS = 5` | `campus_outbox.py` | Timeout for one socket send. |
| `DEFAULT_FLUSH_LIMIT = 50` | `campus_outbox.py` | Rows flushed when a user's socket connects. |
| `EXPIRE_BATCH_LIMIT = 500` | `campus_request_service.py` | Rows handled per expiry sweep. |
| `IDEMPOTENCY_KEY_MAX = 128` | `campus_schema.py` | Maximum length of an idempotency key. |
| `OUTBOX_POLL_DEFAULT_SECONDS = 5.0` | `app/main.py` | Poller interval unless `OUTBOX_POLL_SECONDS` is set. |

---

## 4. Endpoints

Base path: `/api/campus`.

### 4.1 Conventions

- **Authentication.** Every endpoint requires a bearer token (`Authorization: Bearer <jwt>`). A missing or invalid token gives 401.
- **Body and query validation.** Invalid bodies and queries give 422 with FastAPI's default list-shaped `detail`. This includes naive (timezone-less) datetimes and an unknown `timezone` name.
- **Rule errors.** Domain errors use a dict `detail`: `{"code": "<snake_case>", "message": "...", "current": {...}}` for 409, and `{"code": ..., "message": ...}` for 422.
- **Other errors.** Some errors use a plain string `detail`, for example `"Request not found"`, `"Party not found"`, `"Connection not found"` and `"Suggestion not found"`.
- **Ownership.** Owner-only and member-only resources answer 404, never 403, so ids cannot be enumerated. The exceptions are the 403 codes in the party changes table.
- **Times.** Request bodies take offset-aware ISO 8601 datetimes. Responses use this shape:

  ```json
  {"utc": "2026-03-01T18:00:00Z", "local": "2026-03-01T23:30:00+05:30", "timezone": "Asia/Kolkata"}
  ```

- **Idempotency header.** A replayed accept or cancel response has `Idempotent-Replay: true`. Other responses do not carry the header.

### 4.2 Current-state payload in 409 responses

A 409 `current` contains only state the caller is allowed to see:

| Code | `current` contents |
|---|---|
| `stale_version`, `request_not_open`, `use_party_cancel` (request) | `{"request": <caller's own request>}` |
| `overlapping_request` | `{"request": <caller's own clashing request>}` |
| `max_open_requests` | `{"limit": 3}` |
| `not_eligible` | `{"reason": "<rule reason>"}` |
| `duplicate_proposal` | `{"proposal": <proposal as the caller sees it>}` |
| `warnings_unacknowledged` | `{"warnings": [...]}` |
| `already_resolved`, `expired`, `stale_version`, `request_changed`, `participant_busy`, `window_closed`, `not_eligible` on accept | `{"proposal": ..., "active_party": <caller's own AGREED party, or null>}` |
| Party conflicts (`party_not_active`, `party_not_cancellable`, `stale_version`, `change_pending`, `change_not_pending`, `change_no_longer_valid`, `report_too_early`) | `{"party": <party view for the caller>}` |

The caller's own AGREED party is the only party that can appear. Another user's party never appears in a `current` payload. Partner contact details appear in a party view only while the party is AGREED (section 5.6).

### 4.3 Landmarks and requests

| Method | Path | Body or query | Success | Errors |
|---|---|---|---|---|
| GET | `/landmarks` | none | 200 list of `{id, name, kind, latitude, longitude, timezone}`, active landmarks of the caller's college, ordered by kind then name. An account without a college gets `[]`. | 401 |
| POST | `/requests` | `origin_landmark_id`, `hub_id`, `direction` (`TO_HUB` or `FROM_HUB`), `earliest_departure`, `latest_departure` (aware), `arrive_by` (aware, optional), `timezone` (IANA name), `flexibility_consent` (default `false`), `expires_at` (aware, optional) | 201 `TravelRequest` | 422 `college_required`, `invalid_origin_landmark` (origin must be an active CAMPUS_POINT of the caller's college), `invalid_hub_landmark` (hub must be an active HUB of the caller's college), `latest_must_be_after_earliest`, `window_too_short`, `window_too_long`, `window_already_ended`, `window_too_far_ahead`, `arrive_by_before_window`, `invalid_expires_at`. 409 `overlapping_request`, `max_open_requests`. |
| GET | `/requests?status=` | `status` optional, one of OPEN, RESERVED, FULFILLED, CANCELLED, EXPIRED | 200 list, newest first | 422 `invalid_status` |
| GET | `/requests/{id}` | none | 200 `TravelRequest` | 404 `"Request not found"` (also for another user's request) |
| PATCH | `/requests/{id}` | `expected_version` (required), `earliest_departure`, `latest_departure`, `arrive_by`, `flexibility_consent` (all optional) | 200 `TravelRequest` | 404; 409 `request_not_open` (not OPEN), `stale_version`, `overlapping_request`; 422 window codes as above and `arrive_by_before_window`. |
| DELETE | `/requests/{id}` | none | 200 `TravelRequest` | 404; 409 `use_party_cancel` (request is RESERVED). An already-terminal request returns 200 unchanged. |
| GET | `/requests/{id}/suggestions` | none | 200 `{request_id, estimate_status, suggestions, truncated}` | 404 `"Request not found"` |

PATCH details:

- It checks, in order: the request exists and is the caller's, `status` is OPEN, `expected_version` matches, the new window is valid, and there is no overlap. The first failure wins.
- If nothing changes, it returns 200 without incrementing `version`.
- When the window changes, `expires_at` is recalculated from the new `latest_departure`.
- It expires PENDING proposals that touch the request and deletes its suggestion rows.
- Explicit `null` for `earliest_departure`, `latest_departure` or `flexibility_consent` means "unchanged". Explicit `null` for `arrive_by` clears the deadline.

Suggestion item shape (`suggestions[]`):

```json
{
  "id": 1,
  "other": {"user_id": 2, "full_name": "..."},
  "other_request": {"id": 5, "earliest_departure": {...}, "latest_departure": {...}},
  "reason": "WINDOW_OVERLAP",
  "feasible_window": {"start": {...}, "end": {...}},
  "estimate": {"status": "VERIFIED", "distance_m": 9000, "duration_s": 1200, "failure": null, "checked_at": {...}},
  "warnings": [],
  "valid_until": {...},
  "proposal": null
}
```

- `other` has `user_id` and `full_name` only. It never carries contact fields.
- `proposal` is `null`, or `{id, state, direction}` where `direction` is `"outgoing"` or `"incoming"` relative to the caller. It is set when the pair has a PENDING proposal, or an ACCEPTED proposal whose party is still AGREED.
- `estimate_status` is at the top level and per request. A failed routing call gives `UNVERIFIED` with `failure` set to `no_route`, `timeout` or `unavailable`. Suggestions are still returned. An empty list does not mean "no provider data".
- If the request is not OPEN, the response has an empty `suggestions` list and makes no provider call.

### 4.4 Connections

| Method | Path | Body or query | Success | Errors |
|---|---|---|---|---|
| POST | `/suggestions/{suggestion_id}/connections` | `acknowledge_warnings` (default `false`) | 201 `ConnectionOut` (PENDING). Sends `connection_proposed` to the recipient on a socket, best effort. | 404 `"Suggestion not found"` (also when the caller owns neither request). 409 `not_eligible`, `duplicate_proposal`, `warnings_unacknowledged`. |
| GET | `/connections?role=&state=&limit=` | `role` is `all` (default), `incoming` or `outgoing`. `state` optional. `limit` 1 to 200, default 100. | 200 list, newest first | 422 for an invalid `role` or `state`. Expired PENDING proposals are marked EXPIRED before the list is read. |
| POST | `/connections/{id}/accept` | `expected_version` (int, required), `idempotency_key` (1 to 128 characters, required) | 200 `{"connection": ConnectionOut, "party": PartyView}` | 404 `"Connection not found"` (unknown, or the caller is not the recipient). 409 `already_resolved`, `expired`, `stale_version`, `request_changed`, `not_eligible`, `participant_busy`, `window_closed`. 422 `idempotency_key_reused`. |
| POST | `/connections/{id}/decline` | `expected_version` (optional) | 200 `ConnectionOut` (DECLINED). Recipient only. Sends `connection_declined` best effort. | 404 (not the recipient). 409 `already_resolved`, `expired`, `stale_version` (only when `expected_version` is sent). A repeat decline returns 200. |
| POST | `/connections/{id}/withdraw` | `expected_version` (optional) | 200 `ConnectionOut` (WITHDRAWN). Proposer only. Sends `connection_withdrawn` best effort. | 404 (not the proposer). 409 `already_resolved`, `expired`, `stale_version`. A repeat withdraw returns 200. |

Accept, in order: the replay check on `(user, accept_connection, key)`, then the caller's ownership, then the locked checks in the order listed in section 6. A successful accept creates the party, the two members, the events and the outbox rows in one transaction. It then dispatches outbox rows best effort.

Accept detail for `expired`: when the expiry is detected, the server marks the proposal EXPIRED and commits that change before returning the 409.

Accept detail for `window_closed`: when the earliest feasible departure is already past `feasible_end`, the 409 is raised and nothing is committed.

If an accept fails with an unexpected database integrity error and the fallback check finds the proposal still PENDING with no busy participant, the original error is re-raised. This is a server error (500). The fallback does not hide it.

`ConnectionOut` fields: `id`, `suggestion_id`, `state`, `version`, `direction` (`outgoing` or `incoming`), `proposer` and `recipient` (`user_id`, `full_name`), `proposer_request_id`, `recipient_request_id`, `expires_at`, `created_at`, `resolved_at`, `party_id`.

### 4.5 Parties

| Method | Path | Body or query | Success | Errors |
|---|---|---|---|---|
| GET | `/parties/active` | none | 200 `{"party", "recently_ended", "latest_version", "server_time"}`. `party` is the caller's AGREED party or null. `recently_ended` is the caller's most recent COMPLETED, CANCELLED or DISPUTED party that ended within `RECENT_ENDED_HOURS`, or null. `latest_version` is the version of `party`, or of `recently_ended` when there is no active party. | 401 |
| GET | `/parties/{id}` | none | 200 party view | 404 `"Party not found"`. Any member row counts, including inactive (former) members. |
| POST | `/parties/{id}/cancel` | `idempotency_key` (required), `reason` (up to 200 characters), `expected_version` (optional) | 200 party view (CANCELLED) | 404; 409 `party_not_cancellable` (COMPLETED or DISPUTED), `stale_version` (only when `expected_version` is sent and the party is AGREED); 422 `idempotency_key_reused`. |
| POST | `/parties/{id}/changes` | `expected_version` (required), `agreed_departure` (aware, optional), `meeting_landmark_id` (optional), `note` (up to 500 characters, optional). At least one of `agreed_departure` or `meeting_landmark_id` is required. | 201 `ChangeOut` (PENDING) | 404; 409 `party_not_active`, `stale_version`, `change_pending`; 422 `empty_change`, `departure_in_past`, `departure_out_of_range` (more than `MAX_LEAD_DAYS` ahead), `invalid_landmark` (must be an active CAMPUS_POINT of the same college as the current meeting point). |
| POST | `/parties/{id}/changes/{change_id}/approve` | `expected_party_version` (required) | 200 party view (values updated) | 404 `"Party not found"` or `"Change not found"`; 409 `change_not_pending`, `party_not_active`, `stale_version`, `change_no_longer_valid`; 403 `proposer_cannot_decide`. |
| POST | `/parties/{id}/changes/{change_id}/reject` | `expected_party_version` (optional) | 200 `ChangeOut` (REJECTED) | 404; 409 `change_not_pending`, `party_not_active`, `stale_version`; 403 `proposer_cannot_decide`. |
| POST | `/parties/{id}/changes/{change_id}/withdraw` | none | 200 `ChangeOut` (WITHDRAWN) | 404; 409 `change_not_pending`, `party_not_active`; 403 `not_proposer`. |
| PATCH | `/parties/{id}` | `expected_version` (required), `cost_note` (up to 500 characters, nullable) | 200 party view. Emits `NOTE_UPDATED`. No approval is needed. | 404; 409 `party_not_active`, `stale_version`. |
| POST | `/parties/{id}/report` | `outcome`: `COMPLETED` or `DID_NOT_HAPPEN` | 200 party view | 404; 409 `report_too_early` (before `agreed_departure`), `party_not_active`. A repeat of the same outcome returns 200 without a new event. |

Party view fields: `id`, `state`, `version`, `agreed_departure`, `meeting_landmark` (`id`, `name`, `latitude`, `longitude`), `hub`, `direction`, `transport_responsibility`, `cost_note`, `created_at`, `ended_at`, `end_reason`, `members`, `partner`, `pending_change`.

- `members[]`: `user_id`, `full_name`, `request_id`, `you`, `report_outcome`, `reported`. A member's own `report_outcome` is always shown. The partner's `report_outcome` is shown only after the party has ended.
- `partner`: `user_id`, `full_name`, and `phone_number` and `email`, which are non-null only while the party is AGREED.
- `pending_change`: the PENDING change, or null.

A change is proposed by one member and decided by the other. The approval check compares `expected_party_version` with the party version. A PENDING change is marked SUPERSEDED when the party ends. At approval time the change is re-validated: a departure in the past or a no-longer-valid meeting point gives `change_no_longer_valid`.

Party end reasons (`end_reason`): `cancelled_by_member`, `did_not_happen`, `completed`, `disputed`.

### 4.6 Events (reconciliation)

| Method | Path | Query | Success | Errors |
|---|---|---|---|---|
| GET | `/events` | `after_version` (integer, default 0, at least 0), `party_id` (optional) | 200 `{"party_id", "events", "latest_version", "party", "server_time"}` | 404 `"Party not found"` when `party_id` is not one of the caller's parties. |

- Without `party_id`, the server uses the caller's AGREED party, or else the caller's party with the highest id. With no party at all it returns `{"party_id": null, "events": [], "latest_version": null, "party": null}`.
- `events` contains every event with `version > after_version`, ascending. The response is not paginated.
- `party` is the current view. It is not reconstructed from events.
- The call acknowledges the caller's outbox rows for this party up to `latest_version` (section 5.4).

### 4.7 Event payloads

Each event has `version`, `event_type`, `actor_id`, `payload`, `occurred_at`. Payloads, as written by the code:

| Event | Payload |
|---|---|
| `PARTY_AGREED` | `proposal_id`, `agreed_departure`, `member_ids` |
| `CHANGE_PROPOSED` | `change_id`, `new_departure`, `new_meeting_landmark_id` |
| `CHANGE_REJECTED` | `change_id`. A withdrawal is also written as this event type, with `withdrawn: true`. |
| `PARTY_CHANGED` | `change_id`, `agreed_departure`, `meeting_landmark_id` |
| `NOTE_UPDATED` | `field: "cost_note"` |
| `REPORT_RECORDED` | `reported: true`. The outcome is not included (blind reporting). |
| `PARTY_CANCELLED` | `cancelled_by`, `end_reason`, optional `reason`, optional `superseded_change_id`. When the cancellation is a did-not-happen outcome, `end_reason` is `did_not_happen`. |
| `PARTY_COMPLETED` | `end_reason: "completed"`, optional `superseded_change_id` |
| `PARTY_DISPUTED` | `end_reason: "disputed"`, optional `superseded_change_id` |

---

## 5. Reconciliation for clients

### 5.1 Principle

The server is the source of truth. Sockets are an accelerator. A client that has restarted, or that missed a socket message, must converge from REST alone.

### 5.2 Recovery sequence

1. `GET /api/campus/parties/active`. Use `party` (AGREED) and `recently_ended`, and remember `latest_version`.
2. `GET /api/campus/events?party_id=<id>&after_version=<last applied version>`. Use `after_version=0` if the client has no local state.
   - Pass `party_id` explicitly. Without it, the server picks the AGREED party, or the highest-id party. `recently_ended` is chosen by `ended_at`, so the two selections can differ.
3. Replace local state with the returned `party` view. Apply `events` in ascending `version`. `latest_version` is the version the client now matches.

Within a party, `version` only increases. A client should not apply an event whose version is at or below the version it already holds.

### 5.3 Cancel retry

A cancel carries an `idempotency_key`. If the response is lost, the client retries with the same key:

- First success: 200 with the CANCELLED party view. Exactly one `PARTY_CANCELLED` event is recorded.
- Retry with the same key: 200 with `Idempotent-Replay: true`. The body is the stored result, rebuilt for the caller's current state. No new event is recorded.
- A cancel on a party that is already CANCELLED, with a different key: 200 with the current party view. No new event, no replay header.

Accept works the same way: a retry with the same key and the same proposal returns the stored `{connection, party}` with the replay header.

### 5.4 Socket messages and the outbox

Two kinds of socket message exist.

- **Party events**: `{"type": "party_event", "party_id", "version", "event_type"}`. These go through the outbox, described below. The payload has no event content. The client uses `version` to decide whether to call `/events`.
- **Connection messages**: `connection_proposed`, `connection_declined`, `connection_withdrawn`. These are sent once, after commit, on a best-effort basis. They are not in the outbox and are not retried. Clients must reconcile proposals with `GET /connections`.

Outbox rows (`outbox_messages`):

- Each committed party event adds one PENDING row per member.
- Statuses: `PENDING`, `SENT`, `ACKED`, `FAILED`.
  - `SENT`: at least one live socket for the recipient accepted the message. This does not mean the client applied it.
  - `ACKED`: the recipient called `GET /events` with a `latest_version` at or above the event's version.
  - `FAILED`: 8 delivery attempts failed. FAILED rows are never retried. Party state is not affected, and clients still converge through REST.
- Dispatch runs in three places: after each committed party change (for that party), in a background poller, and when the recipient's socket connects. A socket connection ignores retry backoff for that user's PENDING rows.
- The background poller runs every `OUTBOX_POLL_SECONDS` (default 5). A value of 0 or below disables it. An unparseable value falls back to 5 with a warning.
- Each due row is claimed with a conditional update (`status` still PENDING and `next_attempt_at` unchanged). The claim sets `next_attempt_at` to now plus 30 seconds, and it commits before the send. A second dispatcher skips a claimed row. A crashed dispatcher's row becomes due again after the lease.
- A send that times out after 5 seconds, or that raises, or that reaches no socket, counts as a failed attempt. `last_error` records `send_timeout`, `send_error:<ExceptionType>` or `no_live_socket`.
- A failed attempt sets the next attempt to now plus `min(5 * 2^attempts, 300)` seconds, where `attempts` is the count after the increment. The eighth failure sets FAILED.

### 5.5 Blind reporting

`REPORT_RECORDED` does not include the outcome. The other member learns that a report was made, not what it says. The outcome becomes visible to both members when the party ends, through `members[].report_outcome`. The event's `actor_id` identifies the reporter.

### 5.6 Contact visibility

| Surface | What a non-member sees | What a member sees |
|---|---|---|
| Suggestions | Not applicable. Suggestions are only returned to the request owner. | `other` has `user_id` and `full_name` only. |
| Connection proposals | Not applicable. | `proposer` and `recipient` have `user_id` and `full_name` only. |
| Party view | 404 for `GET /parties/{id}` and `/events`. | `partner.phone_number` and `partner.email` are non-null only while the party is AGREED. After the party ends they are null. `full_name` stays. |
| Legacy chat conversation list | The partner's profile fields are null unless the user is an active partner (section 5.7). | Shown for active partners only. |

Party contact is only returned to members of an AGREED party. Other users never see a party.

### 5.7 Chat access

Chat and contact access comes from `backend/app/services/connection_access.py`. Two users are active partners when either holds:

1. The legacy rule: an APPROVED pooling connection, with both pooling requests CONNECTED.
2. The party rule: both are active members of the same AGREED party.

This applies to these checks:

- `users_have_active_ride`, which gates creating a conversation (`find-or-create`) and therefore sending a REST chat message. Once a party has ended and no legacy connection is active, REST sends return 403.
- `get_active_partner_ids`, which gates partner profile fields in the conversation list.
- `authorize_relay`, which gates socket chat relays. It returns the legacy connection or the party. A client-supplied `connection_id` or `party_id` must match the authorized grant. Otherwise the relay is refused. The forwarded payload keeps `connection_id` for legacy grants and adds `party_id` for party grants.

Read access to existing history is membership-based and does not check for an active party. Members can still read messages after a party ends. A non-member gets 403 on conversation history and read receipts.

---

## 6. Concurrency design

### 6.1 Lock order

One global lock order applies across campus code. A transaction takes the levels in ascending order and never takes an earlier level after a later one.

1. User rows, ascending id. Taken with `FOR NO KEY UPDATE` by accept (both participants, in ascending id) and by request create and edit (the owner).
2. Travel request rows, ascending id, `FOR UPDATE`.
3. The travel party row.
4. Party members, proposals, changes and events.

The order is respected by each path:

- Accept: users, then requests, then the other PENDING proposals for those requests (`FOR UPDATE`). The new party row is created in the same transaction, so no other transaction can contend for it.
- Cancel and report: requests, then party, then members.
- Change propose, decide, and note update: party, then change or event rows.
- Proposal creation, decline and withdraw: requests (and the proposal). Decline and withdraw do not lock users.

Expiry sweeps use `SKIP LOCKED` on PostgreSQL. They never wait on another transaction's lock.

### 6.2 Why this order

Two transactions that touch the same rows must acquire them in the same order, or they can deadlock. Locking users first serializes accepts for one student, even when their request locks are disjoint. Without that, two accepts could wait on each other's party-member unique index entries in opposite orders. Member rows are inserted in ascending `user_id` order for the same reason.

### 6.3 Conditional claims and re-checks

- Every decision is re-read and re-checked under the lock (`populate_existing`). A check made before the lock is not trusted.
- Each state change, its event, its outbox rows and its idempotency record are written in one transaction, which is committed. Notifications are sent only after commit. A failed notification never changes committed state.
- The partial unique indexes are the last line of defence. When one fires (`IntegrityError`), the transaction rolls back and the response is rebuilt from fresh state, as a 409 or as a replay.
- Accept retries once on a database `OperationalError` (deadlock or serialization failure), then falls back to a 409.
- Outbox rows are claimed with a conditional update before any send (section 5.4).

### 6.4 Postgres concurrency tests

The tests in `backend/tests/test_campus_party_postgres.py` are opt-in. They are skipped unless `TRIPSYNC_TEST_PG_URL` is set. Each racing operation runs in its own thread with its own session, through the real service functions, released together by a barrier. Each test creates and then drops a throwaway schema. Use a disposable database.

Tests in that file:

- one student accepts two proposals at once
- two students race for one request
- both members cancel at the same time
- a cancel races a change approval
- an accept races a request edit
- cross accepts with two requests per student never deadlock

Run them with a throwaway PostgreSQL 15 container. The credentials below are placeholders.

```bash
docker run --rm -d --name tripsync-campus-pg -p 55432:5432 \
  -e POSTGRES_USER=tripsync -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=tripsync_test \
  postgres:15

cd backend
TRIPSYNC_TEST_PG_URL='postgresql+psycopg2://tripsync:change-me@127.0.0.1:55432/tripsync_test' \
TRIPSYNC_TEST_PG_ITERATIONS=5 \
python -m pytest -q -W ignore -p no:cacheprovider tests/test_campus_party_postgres.py

docker stop tripsync-campus-pg   # --rm removes the container
```

`TRIPSYNC_TEST_PG_ITERATIONS` defaults to 5. A `sqlite:///` URL also works, for a dry run of the same assertions on a file-backed SQLite database.

The CI workflow (`.github/workflows/backend-tests.yml`) runs `python -m pytest -q` without `TRIPSYNC_TEST_PG_URL`. The Postgres tests are skipped there.

### 6.5 What the SQLite suite cannot prove

The default suite runs offline on in-memory SQLite. The Postgres test module states the reason: SQLite serializes writers and ignores `SELECT ... FOR UPDATE`. So the SQLite suite does not prove:

- that the lock order prevents deadlocks
- that row locks prevent lost updates
- that `SKIP LOCKED` behaves as the expiry sweep expects
- that `FOR NO KEY UPDATE` on user rows serializes accepts for one student
- behavior under PostgreSQL's isolation level and commit ordering

The SQLite suite checks the state-machine rules, validation, error payloads and outbox logic. Its threaded tests (for example, concurrent outbox dispatchers in `test_campus_outbox.py`) run on SQLite, so they show that the assertions hold under SQLite's writer serialization. They do not show the PostgreSQL locking behavior above.

---

## 7. Compatibility and migration

### 7.1 Legacy endpoints

The legacy `/api/pool/*` and `/api/chat/*` endpoints keep their routes. The campus endpoints are additive under `/api/campus`.

The campus series (commits `0fb2bb2`, `8cd6e9a`, `e3d9875`, `9944fb8`) changed some shared code. These are behavior extensions:

- `ConnectionManager.send_personal_message` now returns the number of sockets that accepted the message. It previously returned nothing. The outbox relies on the count.
- The chat and pooling WebSocket routers flush the connecting user's pending outbox rows on connect. They pass `party_id` through `authorize_relay`.
- `connection_access.py` also recognizes AGREED parties (section 5.7).
- `router.py` and `main.py` mount the campus routers, import the campus models, and start the outbox poller in the lifespan.

Relative to `main`, this branch also contains earlier, non-campus changes to pooling, map, message and conversation services. This document does not cover those changes.

### 7.2 Schema creation

No migration framework is used. There is no Alembic.

- Startup (`app/main.py`, lifespan) calls `Base.metadata.create_all(bind=engine)`. The demo seed script calls it too.
- `create_all` creates tables that do not exist. An existing database gains the 11 campus tables listed in section 2.
- No existing table is altered on this branch. The campus models are in `campus_model.py`. No existing model file changed.
- Schema changes to campus tables after this point need a migration, because `create_all` will not add columns to existing tables.

### 7.3 Environment variables

| Variable | Default | Effect |
|---|---|---|
| `OUTBOX_POLL_SECONDS` | `5` | Outbox poller interval. `0` or below disables the poller. Each worker process runs its own poller. |
| `DEMO_PASSWORD` | none | Required by the demo seed script. At least 8 characters. Read only from the environment and never printed or logged. |

### 7.4 Demo seed and reset

Run from `backend/`:

```bash
DEMO_PASSWORD=... python -m scripts.seed_demo           # seed (idempotent)
DEMO_PASSWORD=... python -m scripts.seed_demo --reset   # delete demo data only
```

- Seeding creates two demo riders with fictional data, two landmarks ("Main Gate", a campus point, and "Airport Terminal", a hub), and one OPEN request per rider. The requests cover 18:00 to 19:00 and 18:30 to 19:30 Asia/Kolkata on the next local day, on the same corridor. The two riders therefore see each other as a suggestion.
- The script prints the demo account email addresses. It never prints the password.
- `--reset` deletes the demo riders' chat, pooling and campus data, including their requests, suggestions, proposals, parties, events, outbox rows and idempotency records. It releases any other participant's RESERVED request the way a party cancel does. It does not drop tables and does not touch other users' data.

---

## 8. Limitations, non-goals and open decisions

- No payments.
- No dispatch.
- No live location.
- Estimates are optional and may be UNVERIFIED. A failed routing call gives `estimate_status: UNVERIFIED` with a failure code, and suggestions are still returned.
- Sockets are process-local, so the service must run as a single worker. With several workers, a socket on one worker is not visible to another worker's outbox dispatcher. Those rows are retried and eventually FAILED, and clients recover through REST.
- Parties past their departure time without reports stay AGREED. Nothing ends them automatically.
- Completion is self-reported. The server records what each member reports. It does not verify the trip.
- Routing-provider live behaviour is unverified. The test harness blocks outbound `httpx` calls (`conftest.py`), and the provider is faked, so no test reaches the live provider.

Other gaps visible in the code:

- Cancelling a party does not re-match the other member. Their request returns to OPEN or EXPIRED.
- `valid_until` on a suggestion is informational and is not checked when a connection is proposed.
- Connection messages (`connection_proposed`, `connection_declined`, `connection_withdrawn`) are best effort. They are not in the outbox.
- `GET /events` is not paginated.
- A change's `note` is stored but is not applied to the party on approval.

A recorded run of the end-to-end flow is in [docs/campus-demo-transcript.md](campus-demo-transcript.md) (recorded from the acceptance test).

## 9. Acceptance cases

The consolidated acceptance suite is `backend/tests/test_campus_acceptance.py`. It uses only the public HTTP and WebSocket API (real JWT headers), a fake clock, a fake routing provider and a recording socket layer. Run it with `cd backend && .venv/bin/python -m pytest -q -W ignore -p no:cacheprovider tests/test_campus_acceptance.py`.

| Case | Required result | Test |
| --- | --- | --- |
| (a) Compatible future trips posted an hour apart | Both students get a suggestion for each other whatever the age of their requests. Same-direction trips departing hours apart get none. | `test_compatible_future_trips_posted_an_hour_apart_remain_eligible` |
| (b) Opposite direction, disjoint windows, other hub | No suggestion. Flexibility bridges a gap only when both students consent. | `test_opposite_direction_or_disjoint_windows_yield_no_suggestion` |
| (c) Two simultaneous approvals involving one student | Exactly one party and one `PARTY_AGREED` event. The loser gets 409 with only their own state. The losing proposal is `EXPIRED` and its request stays `OPEN`. | `test_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party` (SQLite, threaded); `test_postgres_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party` (opt-in, `TRIPSYNC_TEST_PG_URL`) |
| (d) Cancel while pushes fail and the reply is lost | One `PARTY_CANCELLED` event. After a restart both phones converge on the same version and `CANCELLED` from REST alone. A retry with the same idempotency key replays the stored result. Failed pushes stay `PENDING` and are marked `SENT` by a later dispatcher run. | `test_cancel_offline_then_both_devices_converge_after_restart`; `test_failed_push_is_retried_later_and_marked_sent`; `test_pending_cancel_stays_pending_until_the_server_confirms` |
| (e) Unapproved third user | No party data, no conversation, no message, no socket relay and no contact fields. Chat between members works while `AGREED` and is refused after the end; history stays readable. | `test_unapproved_third_user_cannot_touch_party_chat_or_contact` |
| (f) Provider outage and deadlines | Suggestions are still returned with an `UNVERIFIED` estimate and a failure code, and recover to `VERIFIED`. An `arrive_by` that the earliest feasible departure cannot meet adds `cannot_meet_arrive_by` and proposing requires `acknowledge_warnings`. | `test_provider_outage_never_looks_like_no_partners`; `test_arrive_by_uses_earliest_feasible_departure_*` |

The suite also covers material changes (`test_material_change_requires_both_approvals_end_to_end`), blind completion reports (`test_completion_reports_are_blind_until_both_report`) and the end-to-end demo (`test_full_happy_path_with_two_devices`, which can record [campus-demo-transcript.md](campus-demo-transcript.md)). `test_recorded_recovery_reconciliation_and_competing_accepts` can record [campus-reconciliation-transcript.md](campus-reconciliation-transcript.md).
