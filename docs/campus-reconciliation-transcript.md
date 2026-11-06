# TripSync campus scheduling: recovery transcript

> Recorded from the automated acceptance test with a fake clock and a fake routing provider (no live provider)

Users are fictional. Times come from the test's fake clock, so the transcript is identical on every run.

## 1. A party is AGREED and both phones show the same version

_Setup elided: both students posted requests, searched, Alice proposed and Bob accepted (see the happy-path transcript)._

### 1. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": null,
    "end_reason": null,
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": true, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": false, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 2, "full_name": "Bob Example", "phone_number": "+910000000002", "email": "bob@example.test"},
    "pending_change": null
  },
  "recently_ended": null,
  "latest_version": 1,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 2. alice: `GET /api/campus/events?after_version=0&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 1,
      "event_type": "PARTY_AGREED",
      "actor_id": 2,
      "payload": {"proposal_id": 1, "agreed_departure": "2026-03-01T04:10:00Z", "member_ids": [1, 2]},
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 1,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": null,
    "end_reason": null,
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": true, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": false, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 2, "full_name": "Bob Example", "phone_number": "+910000000002", "email": "bob@example.test"},
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 3. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": null,
    "end_reason": null,
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 1, "full_name": "Alice Example", "phone_number": "+910000000001", "email": "alice@example.test"},
    "pending_change": null
  },
  "recently_ended": null,
  "latest_version": 1,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 4. bob: `GET /api/campus/events?after_version=1&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [],
  "latest_version": 1,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": null,
    "end_reason": null,
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 1, "full_name": "Alice Example", "phone_number": "+910000000001", "email": "alice@example.test"},
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

_Phone state: Alice shows AGREED v1, Bob shows AGREED v1._

## 2. Push delivery is down; Alice cancels; the server commits but the reply is lost

_Client side (not an API call): Alice's phone first writes 'cancel pending' with its idempotency key to local storage, then sends the request._

### 5. alice: `POST /api/campus/parties/1/cancel` -> (response lost before reaching the device)
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{"idempotency_key": "alice-cancel-1"}
```

_Client side (not an API call): the reply never arrives. Alice's phone shows 'cancel pending' and still caches AGREED v1; Bob's phone has heard nothing and shows AGREED v1._

_Server side (asserted by the test, not an API call): exactly one PARTY_CANCELLED event (version 2) exists, and the notification for each member is still pending retry, not lost._

## 3. Alice retries with the SAME idempotency key: stored result, no second event

### 6. alice: `POST /api/campus/parties/1/cancel` -> 200
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{"idempotency_key": "alice-cancel-1"}
```

Response header: `Idempotent-Replay: true`

Response body:
```json
{
  "id": 1,
  "state": "CANCELLED",
  "version": 2,
  "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
  "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
  "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
  "direction": "TO_HUB",
  "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
  "cost_note": null,
  "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
  "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
  "end_reason": "cancelled_by_member",
  "members": [
    {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": true, "report_outcome": null, "reported": false},
    {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": false, "report_outcome": null, "reported": false}
  ],
  "partner": {"user_id": 2, "full_name": "Bob Example", "phone_number": null, "email": null},
  "pending_change": null
}
```

_Phone state: the stored response resolves Alice's 'cancel pending'. The server still holds one PARTY_CANCELLED event._

## 4. Both phones restart with empty caches and converge from REST alone

_Client side (not an API call): both apps restart; every in-memory cache is empty._

### 7. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": true, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": false, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 2, "full_name": "Bob Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "latest_version": 2,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 8. alice: `GET /api/campus/events?after_version=0&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 1,
      "event_type": "PARTY_AGREED",
      "actor_id": 2,
      "payload": {"proposal_id": 1, "agreed_departure": "2026-03-01T04:10:00Z", "member_ids": [1, 2]},
      "occurred_at": "2026-03-01T04:00:00Z"
    },
    {
      "version": 2,
      "event_type": "PARTY_CANCELLED",
      "actor_id": 1,
      "payload": {"cancelled_by": 1, "end_reason": "cancelled_by_member"},
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 2,
  "party": {
    "id": 1,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": true, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": false, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 2, "full_name": "Bob Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 9. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 1, "full_name": "Alice Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "latest_version": 2,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 10. bob: `GET /api/campus/events?after_version=0&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 1,
      "event_type": "PARTY_AGREED",
      "actor_id": 2,
      "payload": {"proposal_id": 1, "agreed_departure": "2026-03-01T04:10:00Z", "member_ids": [1, 2]},
      "occurred_at": "2026-03-01T04:00:00Z"
    },
    {
      "version": 2,
      "event_type": "PARTY_CANCELLED",
      "actor_id": 1,
      "payload": {"cancelled_by": 1, "end_reason": "cancelled_by_member"},
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 2,
  "party": {
    "id": 1,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 1, "full_name": "Alice Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

_Phone state: Alice and Bob both show CANCELLED v2; contact details are null and only names remain._

### 11. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 1, "full_name": "Alice Example", "request_id": 1, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 2, "full_name": "Bob Example", "request_id": 2, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 1, "full_name": "Alice Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "latest_version": 2,
  "server_time": "2026-03-01T04:00:00Z"
}
```

## 5. Bob's request is OPEN again; Alice's is CANCELLED

### 12. bob: `GET /api/campus/requests/2` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "id": 2,
  "user_id": 2,
  "college_id": 1,
  "mode": "SHARED_TAXI_PARTY",
  "origin_landmark_id": 1,
  "hub_id": 2,
  "direction": "TO_HUB",
  "earliest_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
  "latest_departure": {"utc": "2026-03-01T06:00:00Z", "local": "2026-03-01T11:30:00+05:30", "timezone": "Asia/Kolkata"},
  "arrive_by": null,
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "expires_at": {"utc": "2026-03-01T06:00:00Z", "local": "2026-03-01T11:30:00+05:30", "timezone": "Asia/Kolkata"},
  "status": "OPEN",
  "version": 3,
  "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
  "updated_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"}
}
```

### 13. alice: `GET /api/campus/requests/1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "id": 1,
  "user_id": 1,
  "college_id": 1,
  "mode": "SHARED_TAXI_PARTY",
  "origin_landmark_id": 1,
  "hub_id": 2,
  "direction": "TO_HUB",
  "earliest_departure": {"utc": "2026-03-01T04:10:00Z", "local": "2026-03-01T09:40:00+05:30", "timezone": "Asia/Kolkata"},
  "latest_departure": {"utc": "2026-03-01T06:00:00Z", "local": "2026-03-01T11:30:00+05:30", "timezone": "Asia/Kolkata"},
  "arrive_by": null,
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "expires_at": {"utc": "2026-03-01T06:00:00Z", "local": "2026-03-01T11:30:00+05:30", "timezone": "Asia/Kolkata"},
  "status": "CANCELLED",
  "version": 3,
  "created_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"},
  "updated_at": {"utc": "2026-03-01T04:00:00Z", "local": "2026-03-01T09:30:00+05:30", "timezone": "Asia/Kolkata"}
}
```

## 6. Delivery is restored and the outbox dispatcher runs

_Server side (not an API call): the dispatcher finds nothing left to push, because each phone's GET /events already acknowledged its notification. Nothing is pushed twice._

## 7. Same outage, but the phone stays online: the outbox retry delivers later

_Setup elided: Carol and Dave agreed a party._

### 14. carol: `POST /api/campus/parties/2/cancel` -> 200
_clock 2026-03-01T04:01:00Z_

Request body:
```json
{"idempotency_key": "carol-cancel-1"}
```

Response body:
```json
{
  "id": 2,
  "state": "CANCELLED",
  "version": 2,
  "agreed_departure": {"utc": "2026-03-01T04:11:00Z", "local": "2026-03-01T09:41:00+05:30", "timezone": "Asia/Kolkata"},
  "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
  "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
  "direction": "TO_HUB",
  "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
  "cost_note": null,
  "created_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
  "ended_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
  "end_reason": "cancelled_by_member",
  "members": [
    {"user_id": 3, "full_name": "Carol Example", "request_id": 3, "you": true, "report_outcome": null, "reported": false},
    {"user_id": 4, "full_name": "Dave Example", "request_id": 4, "you": false, "report_outcome": null, "reported": false}
  ],
  "partner": {"user_id": 4, "full_name": "Dave Example", "phone_number": null, "email": null},
  "pending_change": null
}
```

_Server side (not an API call): the cancel succeeded for Carol, but both notifications are pending because no socket accepted them._

_Server side (not an API call): delivery is back; once the retry backoff has passed the dispatcher pushes both notifications and marks them sent. A second run pushes nothing._

### 15. dave: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:01:11Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 2,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:11:00Z", "local": "2026-03-01T09:41:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 3, "full_name": "Carol Example", "request_id": 3, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 4, "full_name": "Dave Example", "request_id": 4, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 3, "full_name": "Carol Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "latest_version": 2,
  "server_time": "2026-03-01T04:01:11Z"
}
```

### 16. dave: `GET /api/campus/events?after_version=1&party_id=2` -> 200
_clock 2026-03-01T04:01:11Z_

Response body:
```json
{
  "party_id": 2,
  "events": [
    {
      "version": 2,
      "event_type": "PARTY_CANCELLED",
      "actor_id": 3,
      "payload": {"cancelled_by": 3, "end_reason": "cancelled_by_member"},
      "occurred_at": "2026-03-01T04:01:00Z"
    }
  ],
  "latest_version": 2,
  "party": {
    "id": 2,
    "state": "CANCELLED",
    "version": 2,
    "agreed_departure": {"utc": "2026-03-01T04:11:00Z", "local": "2026-03-01T09:41:00+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": {"utc": "2026-03-01T04:01:00Z", "local": "2026-03-01T09:31:00+05:30", "timezone": "Asia/Kolkata"},
    "end_reason": "cancelled_by_member",
    "members": [
      {"user_id": 3, "full_name": "Carol Example", "request_id": 3, "you": false, "report_outcome": null, "reported": false},
      {"user_id": 4, "full_name": "Dave Example", "request_id": 4, "you": true, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 3, "full_name": "Carol Example", "phone_number": null, "email": null},
    "pending_change": null
  },
  "server_time": "2026-03-01T04:01:11Z"
}
```

_Phone state: even a push is only an accelerator; Dave's reconcile shows CANCELLED v2._

## 8. Two proposals compete for one student: exactly one wins

_The accepts below run one after the other so the transcript is deterministic. The genuinely concurrent proof (threads released by a barrier, SQLite and Postgres) is test_two_simultaneous_approvals_involving_one_student_yield_exactly_one_party._

_Setup elided: Frank and Grace each proposed to Erin._

### 17. erin: `GET /api/campus/connections?role=incoming` -> 200
_clock 2026-03-01T04:01:11Z_

Response body:
```json
[
  {
    "id": 4,
    "suggestion_id": 10,
    "state": "PENDING",
    "version": 1,
    "direction": "incoming",
    "proposer": {"user_id": 7, "full_name": "Grace Example"},
    "recipient": {"user_id": 5, "full_name": "Erin Example"},
    "proposer_request_id": 7,
    "recipient_request_id": 5,
    "expires_at": {"utc": "2026-03-01T04:31:11Z", "local": "2026-03-01T10:01:11+05:30", "timezone": "Asia/Kolkata"},
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "resolved_at": null,
    "party_id": null
  },
  {
    "id": 3,
    "suggestion_id": 6,
    "state": "PENDING",
    "version": 1,
    "direction": "incoming",
    "proposer": {"user_id": 6, "full_name": "Frank Example"},
    "recipient": {"user_id": 5, "full_name": "Erin Example"},
    "proposer_request_id": 6,
    "recipient_request_id": 5,
    "expires_at": {"utc": "2026-03-01T04:31:11Z", "local": "2026-03-01T10:01:11+05:30", "timezone": "Asia/Kolkata"},
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "resolved_at": null,
    "party_id": null
  }
]
```

### 18. erin: `POST /api/campus/connections/3/accept` -> 200
_clock 2026-03-01T04:01:11Z_

Request body:
```json
{"expected_version": 1, "idempotency_key": "erin-accept-frank"}
```

Response body:
```json
{
  "connection": {
    "id": 3,
    "suggestion_id": 6,
    "state": "ACCEPTED",
    "version": 2,
    "direction": "incoming",
    "proposer": {"user_id": 6, "full_name": "Frank Example"},
    "recipient": {"user_id": 5, "full_name": "Erin Example"},
    "proposer_request_id": 6,
    "recipient_request_id": 5,
    "expires_at": {"utc": "2026-03-01T04:31:11Z", "local": "2026-03-01T10:01:11+05:30", "timezone": "Asia/Kolkata"},
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "resolved_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "party_id": 3
  },
  "party": {
    "id": 3,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {"utc": "2026-03-01T04:11:11Z", "local": "2026-03-01T09:41:11+05:30", "timezone": "Asia/Kolkata"},
    "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
    "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "ended_at": null,
    "end_reason": null,
    "members": [
      {"user_id": 5, "full_name": "Erin Example", "request_id": 5, "you": true, "report_outcome": null, "reported": false},
      {"user_id": 6, "full_name": "Frank Example", "request_id": 6, "you": false, "report_outcome": null, "reported": false}
    ],
    "partner": {"user_id": 6, "full_name": "Frank Example", "phone_number": "+910000000006", "email": "frank@example.test"},
    "pending_change": null
  }
}
```

### 19. erin: `POST /api/campus/connections/4/accept` -> 409
_clock 2026-03-01T04:01:11Z_

Request body:
```json
{"expected_version": 1, "idempotency_key": "erin-accept-grace"}
```

Response body:
```json
{
  "detail": {
    "code": "already_resolved",
    "message": "This connection has already been resolved.",
    "current": {
      "proposal": {
        "id": 4,
        "suggestion_id": 10,
        "state": "EXPIRED",
        "version": 2,
        "direction": "incoming",
        "proposer": {"user_id": 7, "full_name": "Grace Example"},
        "recipient": {"user_id": 5, "full_name": "Erin Example"},
        "proposer_request_id": 7,
        "recipient_request_id": 5,
        "expires_at": {"utc": "2026-03-01T04:31:11Z", "local": "2026-03-01T10:01:11+05:30", "timezone": "Asia/Kolkata"},
        "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
        "resolved_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
        "party_id": null
      },
      "active_party": {
        "id": 3,
        "state": "AGREED",
        "version": 1,
        "agreed_departure": {"utc": "2026-03-01T04:11:11Z", "local": "2026-03-01T09:41:11+05:30", "timezone": "Asia/Kolkata"},
        "meeting_landmark": {"id": 1, "name": "Main Gate", "latitude": 19.1, "longitude": 72.84},
        "hub": {"id": 2, "name": "Airport Terminal", "latitude": 19.09, "longitude": 72.87},
        "direction": "TO_HUB",
        "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
        "cost_note": null,
        "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
        "ended_at": null,
        "end_reason": null,
        "members": [
          {"user_id": 5, "full_name": "Erin Example", "request_id": 5, "you": true, "report_outcome": null, "reported": false},
          {"user_id": 6, "full_name": "Frank Example", "request_id": 6, "you": false, "report_outcome": null, "reported": false}
        ],
        "partner": {"user_id": 6, "full_name": "Frank Example", "phone_number": "+910000000006", "email": "frank@example.test"},
        "pending_change": null
      }
    }
  }
}
```

### 20. erin: `GET /api/campus/connections?state=EXPIRED` -> 200
_clock 2026-03-01T04:01:11Z_

Response body:
```json
[
  {
    "id": 4,
    "suggestion_id": 10,
    "state": "EXPIRED",
    "version": 2,
    "direction": "incoming",
    "proposer": {"user_id": 7, "full_name": "Grace Example"},
    "recipient": {"user_id": 5, "full_name": "Erin Example"},
    "proposer_request_id": 7,
    "recipient_request_id": 5,
    "expires_at": {"utc": "2026-03-01T04:31:11Z", "local": "2026-03-01T10:01:11+05:30", "timezone": "Asia/Kolkata"},
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "resolved_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "party_id": null
  }
]
```

### 21. grace: `GET /api/campus/requests` -> 200
_clock 2026-03-01T04:01:11Z_

Response body:
```json
[
  {
    "id": 7,
    "user_id": 7,
    "college_id": 1,
    "mode": "SHARED_TAXI_PARTY",
    "origin_landmark_id": 1,
    "hub_id": 2,
    "direction": "TO_HUB",
    "earliest_departure": {"utc": "2026-03-01T04:11:11Z", "local": "2026-03-01T09:41:11+05:30", "timezone": "Asia/Kolkata"},
    "latest_departure": {"utc": "2026-03-01T06:01:11Z", "local": "2026-03-01T11:31:11+05:30", "timezone": "Asia/Kolkata"},
    "arrive_by": null,
    "timezone": "Asia/Kolkata",
    "flexibility_consent": false,
    "expires_at": {"utc": "2026-03-01T06:01:11Z", "local": "2026-03-01T11:31:11+05:30", "timezone": "Asia/Kolkata"},
    "status": "OPEN",
    "version": 1,
    "created_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"},
    "updated_at": {"utc": "2026-03-01T04:01:11Z", "local": "2026-03-01T09:31:11+05:30", "timezone": "Asia/Kolkata"}
  }
]
```

_Phone state: Erin sees the winning party and Grace's proposal as EXPIRED; Grace's request is still OPEN and searchable._
