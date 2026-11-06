# TripSync campus scheduling: demo transcript

> Recorded from the automated acceptance test with a fake clock and a fake routing provider (no live provider)

Users are fictional. Times come from the test's fake clock, so the transcript is identical on every run.

## 1. Both students look at their campus's landmarks and post a trip request

### 1. alice: `GET /api/campus/landmarks` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
[
  {
    "id": 3,
    "name": "Library",
    "kind": "CAMPUS_POINT",
    "latitude": 19.101,
    "longitude": 72.841,
    "timezone": "Asia/Kolkata"
  },
  {
    "id": 1,
    "name": "Main Gate",
    "kind": "CAMPUS_POINT",
    "latitude": 19.1,
    "longitude": 72.84,
    "timezone": "Asia/Kolkata"
  },
  {
    "id": 2,
    "name": "Airport Terminal",
    "kind": "HUB",
    "latitude": 19.09,
    "longitude": 72.87,
    "timezone": "Asia/Kolkata"
  }
]
```

### 2. alice: `POST /api/campus/requests` -> 201
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "origin_landmark_id": 1,
  "hub_id": 2,
  "direction": "TO_HUB",
  "earliest_departure": "2026-03-01T04:30:00+00:00",
  "latest_departure": "2026-03-01T06:30:00+00:00",
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "arrive_by": "2026-03-01T08:00:00+00:00"
}
```

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
  "earliest_departure": {
    "utc": "2026-03-01T04:30:00Z",
    "local": "2026-03-01T10:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "latest_departure": {
    "utc": "2026-03-01T06:30:00Z",
    "local": "2026-03-01T12:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "arrive_by": {
    "utc": "2026-03-01T08:00:00Z",
    "local": "2026-03-01T13:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "expires_at": {
    "utc": "2026-03-01T06:30:00Z",
    "local": "2026-03-01T12:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "status": "OPEN",
  "version": 1,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "updated_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  }
}
```

### 3. bob: `POST /api/campus/requests` -> 201
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "origin_landmark_id": 1,
  "hub_id": 2,
  "direction": "TO_HUB",
  "earliest_departure": "2026-03-01T05:00:00+00:00",
  "latest_departure": "2026-03-01T07:00:00+00:00",
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false
}
```

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
  "earliest_departure": {
    "utc": "2026-03-01T05:00:00Z",
    "local": "2026-03-01T10:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "latest_departure": {
    "utc": "2026-03-01T07:00:00Z",
    "local": "2026-03-01T12:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "arrive_by": null,
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "expires_at": {
    "utc": "2026-03-01T07:00:00Z",
    "local": "2026-03-01T12:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "status": "OPEN",
  "version": 1,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "updated_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  }
}
```

## 2. Each searches: the windows overlap, the estimate comes from the (fake) provider

### 4. alice: `GET /api/campus/requests/1/suggestions` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "request_id": 1,
  "estimate_status": "VERIFIED",
  "suggestions": [
    {
      "id": 1,
      "other": {
        "user_id": 2,
        "full_name": "Bob Example"
      },
      "other_request": {
        "id": 2,
        "earliest_departure": {
          "utc": "2026-03-01T05:00:00Z",
          "local": "2026-03-01T10:30:00+05:30",
          "timezone": "Asia/Kolkata"
        },
        "latest_departure": {
          "utc": "2026-03-01T07:00:00Z",
          "local": "2026-03-01T12:30:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "reason": "WINDOW_OVERLAP",
      "feasible_window": {
        "start": {
          "utc": "2026-03-01T05:00:00Z",
          "local": "2026-03-01T10:30:00+05:30",
          "timezone": "Asia/Kolkata"
        },
        "end": {
          "utc": "2026-03-01T06:30:00Z",
          "local": "2026-03-01T12:00:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "estimate": {
        "status": "VERIFIED",
        "distance_m": 12000,
        "duration_s": 1800,
        "failure": null,
        "checked_at": {
          "utc": "2026-03-01T04:00:00Z",
          "local": "2026-03-01T09:30:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "warnings": [],
      "valid_until": {
        "utc": "2026-03-01T04:15:00Z",
        "local": "2026-03-01T09:45:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "proposal": null
    }
  ],
  "truncated": false
}
```

### 5. bob: `GET /api/campus/requests/2/suggestions` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "request_id": 2,
  "estimate_status": "VERIFIED",
  "suggestions": [
    {
      "id": 1,
      "other": {
        "user_id": 1,
        "full_name": "Alice Example"
      },
      "other_request": {
        "id": 1,
        "earliest_departure": {
          "utc": "2026-03-01T04:30:00Z",
          "local": "2026-03-01T10:00:00+05:30",
          "timezone": "Asia/Kolkata"
        },
        "latest_departure": {
          "utc": "2026-03-01T06:30:00Z",
          "local": "2026-03-01T12:00:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "reason": "WINDOW_OVERLAP",
      "feasible_window": {
        "start": {
          "utc": "2026-03-01T05:00:00Z",
          "local": "2026-03-01T10:30:00+05:30",
          "timezone": "Asia/Kolkata"
        },
        "end": {
          "utc": "2026-03-01T06:30:00Z",
          "local": "2026-03-01T12:00:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "estimate": {
        "status": "VERIFIED",
        "distance_m": 12000,
        "duration_s": 1800,
        "failure": null,
        "checked_at": {
          "utc": "2026-03-01T04:00:00Z",
          "local": "2026-03-01T09:30:00+05:30",
          "timezone": "Asia/Kolkata"
        }
      },
      "warnings": [],
      "valid_until": {
        "utc": "2026-03-01T04:15:00Z",
        "local": "2026-03-01T09:45:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "proposal": null
    }
  ],
  "truncated": false
}
```

## 3. Alice proposes, Bob sees it as incoming and accepts: a party is agreed

### 6. alice: `POST /api/campus/suggestions/1/connections` -> 201
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "acknowledge_warnings": false
}
```

Response body:
```json
{
  "id": 1,
  "suggestion_id": 1,
  "state": "PENDING",
  "version": 1,
  "direction": "outgoing",
  "proposer": {
    "user_id": 1,
    "full_name": "Alice Example"
  },
  "recipient": {
    "user_id": 2,
    "full_name": "Bob Example"
  },
  "proposer_request_id": 1,
  "recipient_request_id": 2,
  "expires_at": {
    "utc": "2026-03-01T04:30:00Z",
    "local": "2026-03-01T10:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "resolved_at": null,
  "party_id": null
}
```

### 7. bob: `GET /api/campus/connections?role=incoming` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
[
  {
    "id": 1,
    "suggestion_id": 1,
    "state": "PENDING",
    "version": 1,
    "direction": "incoming",
    "proposer": {
      "user_id": 1,
      "full_name": "Alice Example"
    },
    "recipient": {
      "user_id": 2,
      "full_name": "Bob Example"
    },
    "proposer_request_id": 1,
    "recipient_request_id": 2,
    "expires_at": {
      "utc": "2026-03-01T04:30:00Z",
      "local": "2026-03-01T10:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "resolved_at": null,
    "party_id": null
  }
]
```

### 8. bob: `POST /api/campus/connections/1/accept` -> 200
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "expected_version": 1,
  "idempotency_key": "bob-accept-1"
}
```

Response body:
```json
{
  "connection": {
    "id": 1,
    "suggestion_id": 1,
    "state": "ACCEPTED",
    "version": 2,
    "direction": "incoming",
    "proposer": {
      "user_id": 1,
      "full_name": "Alice Example"
    },
    "recipient": {
      "user_id": 2,
      "full_name": "Bob Example"
    },
    "proposer_request_id": 1,
    "recipient_request_id": 2,
    "expires_at": {
      "utc": "2026-03-01T04:30:00Z",
      "local": "2026-03-01T10:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "resolved_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "party_id": 1
  },
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {
      "utc": "2026-03-01T05:00:00Z",
      "local": "2026-03-01T10:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": "+910000000001",
      "email": "alice@example.test"
    },
    "pending_change": null
  }
}
```

## 4. Alice's phone reconciles over REST (sockets are only an accelerator)

### 9. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {
      "utc": "2026-03-01T05:00:00Z",
      "local": "2026-03-01T10:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": "+910000000002",
      "email": "bob@example.test"
    },
    "pending_change": null
  },
  "recently_ended": null,
  "latest_version": 1,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 10. alice: `GET /api/campus/events?after_version=0&party_id=1` -> 200
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
      "payload": {
        "proposal_id": 1,
        "agreed_departure": "2026-03-01T05:00:00Z",
        "member_ids": [
          1,
          2
        ]
      },
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 1,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 1,
    "agreed_departure": {
      "utc": "2026-03-01T05:00:00Z",
      "local": "2026-03-01T10:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": "+910000000002",
      "email": "bob@example.test"
    },
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

## 5. They chat while the party is AGREED

### 11. alice: `GET /api/chat/conversations/find-or-create?partner_id=2` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "conversation_id": 1,
  "partner": {
    "id": 2,
    "full_name": "Bob Example",
    "email": "bob@example.test"
  }
}
```

### 12. alice: `POST /api/chat/messages` -> 200
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "receiver_id": 2,
  "content": "I'll wait at the gate"
}
```

Response body:
```json
{
  "id": 1,
  "conversation_id": 1,
  "sender_id": 1,
  "sender_name": "Alice Example",
  "content": "I'll wait at the gate",
  "created_at": "2026-03-01T04:00:00",
  "is_read": false
}
```

### 13. bob: `POST /api/chat/messages/1/read` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "marked_read": 1
}
```

### 14. bob: `GET /api/chat/messages/1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "messages": [
    {
      "id": 1,
      "conversation_id": 1,
      "sender_id": 1,
      "sender_name": "Alice Example",
      "content": "I'll wait at the gate",
      "created_at": "2026-03-01T04:00:00",
      "is_read": true
    }
  ]
}
```

## 6. A material change (new departure) needs the other member's approval

### 15. alice: `POST /api/campus/parties/1/changes` -> 201
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "expected_version": 1,
  "agreed_departure": "2026-03-01T05:30:00+00:00",
  "note": "10 minutes later please"
}
```

Response body:
```json
{
  "id": 1,
  "party_id": 1,
  "proposer_id": 1,
  "new_departure": {
    "utc": "2026-03-01T05:30:00Z",
    "local": "2026-03-01T11:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "new_meeting_landmark": null,
  "note": "10 minutes later please",
  "expected_party_version": 1,
  "state": "PENDING",
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "resolved_at": null,
  "resolved_by": null
}
```

### 16. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 2,
    "agreed_departure": {
      "utc": "2026-03-01T05:00:00Z",
      "local": "2026-03-01T10:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": "+910000000001",
      "email": "alice@example.test"
    },
    "pending_change": {
      "id": 1,
      "party_id": 1,
      "proposer_id": 1,
      "new_departure": {
        "utc": "2026-03-01T05:30:00Z",
        "local": "2026-03-01T11:00:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "new_meeting_landmark": null,
      "note": "10 minutes later please",
      "expected_party_version": 1,
      "state": "PENDING",
      "created_at": {
        "utc": "2026-03-01T04:00:00Z",
        "local": "2026-03-01T09:30:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "resolved_at": null,
      "resolved_by": null
    }
  },
  "recently_ended": null,
  "latest_version": 2,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 17. bob: `GET /api/campus/events?after_version=1&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 2,
      "event_type": "CHANGE_PROPOSED",
      "actor_id": 1,
      "payload": {
        "change_id": 1,
        "new_departure": "2026-03-01T05:30:00Z",
        "new_meeting_landmark_id": null
      },
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 2,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 2,
    "agreed_departure": {
      "utc": "2026-03-01T05:00:00Z",
      "local": "2026-03-01T10:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": "+910000000001",
      "email": "alice@example.test"
    },
    "pending_change": {
      "id": 1,
      "party_id": 1,
      "proposer_id": 1,
      "new_departure": {
        "utc": "2026-03-01T05:30:00Z",
        "local": "2026-03-01T11:00:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "new_meeting_landmark": null,
      "note": "10 minutes later please",
      "expected_party_version": 1,
      "state": "PENDING",
      "created_at": {
        "utc": "2026-03-01T04:00:00Z",
        "local": "2026-03-01T09:30:00+05:30",
        "timezone": "Asia/Kolkata"
      },
      "resolved_at": null,
      "resolved_by": null
    }
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 18. bob: `POST /api/campus/parties/1/changes/1/approve` -> 200
_clock 2026-03-01T04:00:00Z_

Request body:
```json
{
  "expected_party_version": 2
}
```

Response body:
```json
{
  "id": 1,
  "state": "AGREED",
  "version": 3,
  "agreed_departure": {
    "utc": "2026-03-01T05:30:00Z",
    "local": "2026-03-01T11:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "meeting_landmark": {
    "id": 1,
    "name": "Main Gate",
    "latitude": 19.1,
    "longitude": 72.84
  },
  "hub": {
    "id": 2,
    "name": "Airport Terminal",
    "latitude": 19.09,
    "longitude": 72.87
  },
  "direction": "TO_HUB",
  "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
  "cost_note": null,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "ended_at": null,
  "end_reason": null,
  "members": [
    {
      "user_id": 1,
      "full_name": "Alice Example",
      "request_id": 1,
      "you": false,
      "report_outcome": null,
      "reported": false
    },
    {
      "user_id": 2,
      "full_name": "Bob Example",
      "request_id": 2,
      "you": true,
      "report_outcome": null,
      "reported": false
    }
  ],
  "partner": {
    "user_id": 1,
    "full_name": "Alice Example",
    "phone_number": "+910000000001",
    "email": "alice@example.test"
  },
  "pending_change": null
}
```

### 19. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 3,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": "+910000000002",
      "email": "bob@example.test"
    },
    "pending_change": null
  },
  "recently_ended": null,
  "latest_version": 3,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 20. alice: `GET /api/campus/events?after_version=1&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 2,
      "event_type": "CHANGE_PROPOSED",
      "actor_id": 1,
      "payload": {
        "change_id": 1,
        "new_departure": "2026-03-01T05:30:00Z",
        "new_meeting_landmark_id": null
      },
      "occurred_at": "2026-03-01T04:00:00Z"
    },
    {
      "version": 3,
      "event_type": "PARTY_CHANGED",
      "actor_id": 2,
      "payload": {
        "change_id": 1,
        "agreed_departure": "2026-03-01T05:30:00Z",
        "meeting_landmark_id": 1
      },
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 3,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 3,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": "+910000000002",
      "email": "bob@example.test"
    },
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 21. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 3,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": "+910000000001",
      "email": "alice@example.test"
    },
    "pending_change": null
  },
  "recently_ended": null,
  "latest_version": 3,
  "server_time": "2026-03-01T04:00:00Z"
}
```

### 22. bob: `GET /api/campus/events?after_version=2&party_id=1` -> 200
_clock 2026-03-01T04:00:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 3,
      "event_type": "PARTY_CHANGED",
      "actor_id": 2,
      "payload": {
        "change_id": 1,
        "agreed_departure": "2026-03-01T05:30:00Z",
        "meeting_landmark_id": 1
      },
      "occurred_at": "2026-03-01T04:00:00Z"
    }
  ],
  "latest_version": 3,
  "party": {
    "id": 1,
    "state": "AGREED",
    "version": 3,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": null,
    "end_reason": null,
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": null,
        "reported": false
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": null,
        "reported": false
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": "+910000000001",
      "email": "alice@example.test"
    },
    "pending_change": null
  },
  "server_time": "2026-03-01T04:00:00Z"
}
```

## 7. After the departure both report; completion is self-reported, not GPS proof

### 23. alice: `POST /api/campus/parties/1/report` -> 200
_clock 2026-03-01T05:40:00Z_

Request body:
```json
{
  "outcome": "COMPLETED"
}
```

Response body:
```json
{
  "id": 1,
  "state": "AGREED",
  "version": 4,
  "agreed_departure": {
    "utc": "2026-03-01T05:30:00Z",
    "local": "2026-03-01T11:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "meeting_landmark": {
    "id": 1,
    "name": "Main Gate",
    "latitude": 19.1,
    "longitude": 72.84
  },
  "hub": {
    "id": 2,
    "name": "Airport Terminal",
    "latitude": 19.09,
    "longitude": 72.87
  },
  "direction": "TO_HUB",
  "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
  "cost_note": null,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "ended_at": null,
  "end_reason": null,
  "members": [
    {
      "user_id": 1,
      "full_name": "Alice Example",
      "request_id": 1,
      "you": true,
      "report_outcome": "COMPLETED",
      "reported": true
    },
    {
      "user_id": 2,
      "full_name": "Bob Example",
      "request_id": 2,
      "you": false,
      "report_outcome": null,
      "reported": false
    }
  ],
  "partner": {
    "user_id": 2,
    "full_name": "Bob Example",
    "phone_number": "+910000000002",
    "email": "bob@example.test"
  },
  "pending_change": null
}
```

### 24. bob: `POST /api/campus/parties/1/report` -> 200
_clock 2026-03-01T05:40:00Z_

Request body:
```json
{
  "outcome": "COMPLETED"
}
```

Response body:
```json
{
  "id": 1,
  "state": "COMPLETED",
  "version": 6,
  "agreed_departure": {
    "utc": "2026-03-01T05:30:00Z",
    "local": "2026-03-01T11:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "meeting_landmark": {
    "id": 1,
    "name": "Main Gate",
    "latitude": 19.1,
    "longitude": 72.84
  },
  "hub": {
    "id": 2,
    "name": "Airport Terminal",
    "latitude": 19.09,
    "longitude": 72.87
  },
  "direction": "TO_HUB",
  "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
  "cost_note": null,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "ended_at": {
    "utc": "2026-03-01T05:40:00Z",
    "local": "2026-03-01T11:10:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "end_reason": "completed",
  "members": [
    {
      "user_id": 1,
      "full_name": "Alice Example",
      "request_id": 1,
      "you": false,
      "report_outcome": "COMPLETED",
      "reported": true
    },
    {
      "user_id": 2,
      "full_name": "Bob Example",
      "request_id": 2,
      "you": true,
      "report_outcome": "COMPLETED",
      "reported": true
    }
  ],
  "partner": {
    "user_id": 1,
    "full_name": "Alice Example",
    "phone_number": null,
    "email": null
  },
  "pending_change": null
}
```

### 25. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "COMPLETED",
    "version": 6,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": {
      "utc": "2026-03-01T05:40:00Z",
      "local": "2026-03-01T11:10:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "end_reason": "completed",
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": "COMPLETED",
        "reported": true
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": "COMPLETED",
        "reported": true
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": null,
      "email": null
    },
    "pending_change": null
  },
  "latest_version": 6,
  "server_time": "2026-03-01T05:40:00Z"
}
```

### 26. alice: `GET /api/campus/events?after_version=3&party_id=1` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 4,
      "event_type": "REPORT_RECORDED",
      "actor_id": 1,
      "payload": {
        "reported": true
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    },
    {
      "version": 5,
      "event_type": "REPORT_RECORDED",
      "actor_id": 2,
      "payload": {
        "reported": true
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    },
    {
      "version": 6,
      "event_type": "PARTY_COMPLETED",
      "actor_id": 2,
      "payload": {
        "end_reason": "completed"
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    }
  ],
  "latest_version": 6,
  "party": {
    "id": 1,
    "state": "COMPLETED",
    "version": 6,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": {
      "utc": "2026-03-01T05:40:00Z",
      "local": "2026-03-01T11:10:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "end_reason": "completed",
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": "COMPLETED",
        "reported": true
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": "COMPLETED",
        "reported": true
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": null,
      "email": null
    },
    "pending_change": null
  },
  "server_time": "2026-03-01T05:40:00Z"
}
```

### 27. bob: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "COMPLETED",
    "version": 6,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": {
      "utc": "2026-03-01T05:40:00Z",
      "local": "2026-03-01T11:10:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "end_reason": "completed",
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": "COMPLETED",
        "reported": true
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": "COMPLETED",
        "reported": true
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": null,
      "email": null
    },
    "pending_change": null
  },
  "latest_version": 6,
  "server_time": "2026-03-01T05:40:00Z"
}
```

### 28. bob: `GET /api/campus/events?after_version=3&party_id=1` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "party_id": 1,
  "events": [
    {
      "version": 4,
      "event_type": "REPORT_RECORDED",
      "actor_id": 1,
      "payload": {
        "reported": true
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    },
    {
      "version": 5,
      "event_type": "REPORT_RECORDED",
      "actor_id": 2,
      "payload": {
        "reported": true
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    },
    {
      "version": 6,
      "event_type": "PARTY_COMPLETED",
      "actor_id": 2,
      "payload": {
        "end_reason": "completed"
      },
      "occurred_at": "2026-03-01T05:40:00Z"
    }
  ],
  "latest_version": 6,
  "party": {
    "id": 1,
    "state": "COMPLETED",
    "version": 6,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": {
      "utc": "2026-03-01T05:40:00Z",
      "local": "2026-03-01T11:10:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "end_reason": "completed",
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": false,
        "report_outcome": "COMPLETED",
        "reported": true
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": true,
        "report_outcome": "COMPLETED",
        "reported": true
      }
    ],
    "partner": {
      "user_id": 1,
      "full_name": "Alice Example",
      "phone_number": null,
      "email": null
    },
    "pending_change": null
  },
  "server_time": "2026-03-01T05:40:00Z"
}
```

## 8. Afterwards: contact details are hidden and chat is closed, history stays

### 29. alice: `GET /api/campus/parties/active` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "party": null,
  "recently_ended": {
    "id": 1,
    "state": "COMPLETED",
    "version": 6,
    "agreed_departure": {
      "utc": "2026-03-01T05:30:00Z",
      "local": "2026-03-01T11:00:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "meeting_landmark": {
      "id": 1,
      "name": "Main Gate",
      "latitude": 19.1,
      "longitude": 72.84
    },
    "hub": {
      "id": 2,
      "name": "Airport Terminal",
      "latitude": 19.09,
      "longitude": 72.87
    },
    "direction": "TO_HUB",
    "transport_responsibility": "Participants arrange and pay for the taxi themselves. This agreement is not a booking, ...",
    "cost_note": null,
    "created_at": {
      "utc": "2026-03-01T04:00:00Z",
      "local": "2026-03-01T09:30:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "ended_at": {
      "utc": "2026-03-01T05:40:00Z",
      "local": "2026-03-01T11:10:00+05:30",
      "timezone": "Asia/Kolkata"
    },
    "end_reason": "completed",
    "members": [
      {
        "user_id": 1,
        "full_name": "Alice Example",
        "request_id": 1,
        "you": true,
        "report_outcome": "COMPLETED",
        "reported": true
      },
      {
        "user_id": 2,
        "full_name": "Bob Example",
        "request_id": 2,
        "you": false,
        "report_outcome": "COMPLETED",
        "reported": true
      }
    ],
    "partner": {
      "user_id": 2,
      "full_name": "Bob Example",
      "phone_number": null,
      "email": null
    },
    "pending_change": null
  },
  "latest_version": 6,
  "server_time": "2026-03-01T05:40:00Z"
}
```

### 30. alice: `POST /api/chat/messages` -> 403
_clock 2026-03-01T05:40:00Z_

Request body:
```json
{
  "receiver_id": 2,
  "content": "thanks!"
}
```

Response body:
```json
{
  "detail": "Chat is only available with an approved ride partner"
}
```

### 31. alice: `GET /api/chat/messages/1` -> 200
_clock 2026-03-01T05:40:00Z_

Response body:
```json
{
  "messages": [
    {
      "id": 1,
      "conversation_id": 1,
      "sender_id": 1,
      "sender_name": "Alice Example",
      "content": "I'll wait at the gate",
      "created_at": "2026-03-01T04:00:00",
      "is_read": true
    }
  ]
}
```

### 32. alice: `GET /api/campus/requests/1` -> 200
_clock 2026-03-01T05:40:00Z_

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
  "earliest_departure": {
    "utc": "2026-03-01T04:30:00Z",
    "local": "2026-03-01T10:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "latest_departure": {
    "utc": "2026-03-01T06:30:00Z",
    "local": "2026-03-01T12:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "arrive_by": {
    "utc": "2026-03-01T08:00:00Z",
    "local": "2026-03-01T13:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "timezone": "Asia/Kolkata",
  "flexibility_consent": false,
  "expires_at": {
    "utc": "2026-03-01T06:30:00Z",
    "local": "2026-03-01T12:00:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "status": "FULFILLED",
  "version": 3,
  "created_at": {
    "utc": "2026-03-01T04:00:00Z",
    "local": "2026-03-01T09:30:00+05:30",
    "timezone": "Asia/Kolkata"
  },
  "updated_at": {
    "utc": "2026-03-01T05:40:00Z",
    "local": "2026-03-01T11:10:00+05:30",
    "timezone": "Asia/Kolkata"
  }
}
```
