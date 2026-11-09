# TripSync Backend

Backend service for **TripSync**, built with **FastAPI** and **Uvicorn**.
The API runs locally with Uvicorn. Docker Compose starts only PostgreSQL and Adminer.

---

## 🔧 Environment Setup

Copy the template and edit the placeholders in `.env`:

```bash
cp .env.example .env
```

`backend/.env.example` lists every variable the app reads, with placeholder values.
Never commit `.env`.

---

## 🚀 Run Locally

```bash
# Go to backend folder
cd backend

# Create and activate a virtual environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate   # Linux / Mac
.venv\Scripts\activate      # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Create or upgrade the database schema (PostgreSQL)
alembic upgrade head

# Start FastAPI server (one worker: rate limits and caches live in process memory)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Server will run at:** 👉 http://localhost:8000

For a quick local run without Postgres, set `DATABASE_URL=sqlite:///./tripsync.db`:
the app then creates the tables itself at startup (see Migrations below).

---

## Configuration

All settings are environment variables (or `backend/.env`); `.env.example` lists them with defaults.

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `TripSync` | API title, email subjects, root message |
| `DATABASE_URL` | (required) | SQLAlchemy URL |
| `DB_AUTO_CREATE` | on for `sqlite://`, else off | Run `create_all` at startup (development convenience) |
| `ALLOW_ORIGINS` | (required) | CORS origins, comma-separated. `*` allows any origin and turns credentials off |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | (required) | Access tokens; the secret also keys the HMAC of email codes |
| `COLLEGE_EMAIL_DOMAINS` | `{}` | JSON object, college name -> accepted email domains (see Registration) |
| `EMAIL_BACKEND` | `console` | `console` or `smtp` (see Email) |
| `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (true), `SMTP_TIMEOUT_SECONDS` (10), `EMAIL_FROM` | | SMTP delivery |
| `RATE_LIMIT_ENABLED` and `RATE_LIMIT_*` | on | See Rate limits |
| `TRUSTED_PROXY`, `TRUSTED_PROXY_HOPS` | `false`, `1` | Take the client IP from `X-Forwarded-For` (only behind your own proxy) |
| `OLA_MAPS_API_KEY` | (required) | Server-side Ola Maps key (routes and places) |
| `OLA_MAPS_PROXY` | unset | HTTP proxy for every Ola Maps request |
| `PLACES_CACHE_TTL_SECONDS`, `ROUTE_CACHE_TTL_SECONDS`, `MAPS_CACHE_MAX_ENTRIES` | 600, 120, 1000 | In-memory maps caches |

---

## Migrations

The schema is managed with Alembic (`alembic.ini`, `migrations/`). Run from `backend/`:

```bash
alembic upgrade head                      # create or upgrade the database in DATABASE_URL
alembic upgrade head -x url=<sqlalchemy-url>   # target another database
alembic revision --autogenerate -m "..."  # after changing models; review the generated file
alembic check                             # fails if the models and the migrations differ
```

- **New PostgreSQL database:** `alembic upgrade head`.
- **Existing database created by the app's old `create_all`** (before Alembic was added): run
  `alembic stamp 0001_baseline` once, then `alembic upgrade head`.
- **SQLite development:** with `DB_AUTO_CREATE` on (the default for `sqlite://` URLs) the app
  runs `create_all` at startup and, for an empty database, stamps the Alembic head. `create_all`
  never alters existing tables, so an older local SQLite file needs `alembic stamp 0001_baseline`
  plus `alembic upgrade head`, or a fresh file.
- Leave `DB_AUTO_CREATE` off for PostgreSQL; deployments run `alembic upgrade head` before starting the app.

`0002_auth_verification` adds college email domains, the user columns for date of birth, email
verification, token revocation and deactivation, and the `email_codes` table. Existing
accounts stay unverified and are asked to verify their email at their next login.

---

## Registration, verification and login

- `GET /api/auth/colleges` lists colleges open for registration with their email domains.
  Domains come from built-in defaults (`DJSCE` -> `djsce.ac.in`; every other college closed)
  overridden by `COLLEGE_EMAIL_DOMAINS`, e.g. `{"SPIT": ["spit.ac.in"]}`. The app upserts the
  college list from these settings at every startup, so the setting is the source of truth.
- `POST /api/auth/register` needs a college email domain, an age of 18+ (server date), and a
  password of 8+ characters and at most 72 UTF-8 bytes. Emails are trimmed and lowercased. It
  emails a 6-digit code.
- `POST /api/auth/verify-email/confirm` checks the code and returns a token. Codes expire after
  10 minutes, allow 5 wrong attempts and are stored only as HMAC-SHA256 hashes.
  `POST /api/auth/verify-email/request` sends a new one (at most one per address per 60 s;
  same answer for every address).
- `POST /api/auth/token` (OAuth2 form) answers 403 `email_not_verified` while the address is unconfirmed.
- `POST /api/auth/password/forgot` / `reset` (emailed code) and `POST /api/auth/password/change`
  (signed in) set a new password and revoke every older token.
- Tokens carry `sub` = user id and `tv` = the user's token version; deactivated users
  (`users.is_active = false`) and revoked tokens get 401 on REST and WebSockets.
- Errors on these endpoints use `{"detail": {"code": "...", "message": "..."}}`. Malformed
  requests answer 422 with code `invalid_request`.

## Email

- `EMAIL_BACKEND=console` (default) does not send anything: it logs
  `Verification code for s***@college.ac.in: 123456` at WARNING so you can sign up locally.
  Never use it in production.
- `EMAIL_BACKEND=smtp` sends through `SMTP_HOST:SMTP_PORT` with STARTTLS (`SMTP_STARTTLS=true`),
  logging in with `SMTP_USER`/`SMTP_PASSWORD` when set, from `EMAIL_FROM`. Codes are never logged.
- Emails are sent after the request's database work commits; delivery failures are logged
  (without the code) and never change the HTTP response.

## Rate limits

An in-process sliding-window limiter returns 429
`{"detail": {"code": "too_many_requests", "message": ..., "retry_after_seconds": N}}` with a
`Retry-After` header. It keeps counters in memory, so it assumes **one worker process**; with
several workers or hosts each enforces its own copy (move to a shared store before scaling out).

| Rule (`RATE_LIMIT_...`) | Default | Applies to |
|---|---|---|
| `LOGIN_IP`, `LOGIN_EMAIL` | 60/300 s, 10/600 s | `POST /auth/token` |
| `REGISTER_IP` | 60/3600 s | `POST /auth/register` |
| `VERIFY_REQUEST_IP` | 60/3600 s | `POST /auth/verify-email/request` (plus the 60 s per-address cooldown) |
| `VERIFY_CONFIRM_IP`, `VERIFY_CONFIRM_EMAIL` | 60/600 s, 10/600 s | `POST /auth/verify-email/confirm` |
| `PASSWORD_FORGOT_IP` | 30/3600 s | `POST /auth/password/forgot` |
| `PASSWORD_RESET_IP`, `PASSWORD_RESET_EMAIL` | 60/600 s, 10/600 s | `POST /auth/password/reset` |
| `PLACES_USER` | 60/60 s | `GET /map/places/*` |
| `ROUTE_USER` | 30/60 s | `POST /map/route` |
| `CHAT_MESSAGE_USER` | 30/60 s | `POST /chat/messages` |

Rules are `"<count>/<seconds>"`; `off` disables one rule and `RATE_LIMIT_ENABLED=false` all of
them. The client IP is the socket peer address; set `TRUSTED_PROXY=true` (and
`TRUSTED_PROXY_HOPS`) only when a reverse proxy you control sets `X-Forwarded-For`.

## Places proxy

`GET /api/map/places/autocomplete?input=&lat=&lng=`, `/places/details?place_id=` and
`/places/reverse-geocode?lat=&lng=` call Ola Maps with the server-side key (the app never sees
it) and return small normalised shapes. They need a bearer token, are rate limited per user and
cached in memory (`PLACES_CACHE_TTL_SECONDS`, bounded by `MAPS_CACHE_MAX_ENTRIES`). Failures map
to 502 `maps_unavailable`, 504 `maps_timeout` and 422 `invalid_request`. Search text and
coordinates are never logged above DEBUG. `POST /api/map/route` also caches found routes for
`ROUTE_CACHE_TTL_SECONDS`.

## Health

- `GET /api/health/ping`: process is up.
- `GET /api/health/ready`: 200 `{"status": "ok", "database": "ok"}` when `SELECT 1` succeeds,
  503 `{"status": "degraded", "database": "error"}` otherwise.

---

## 🐳 Database with Docker Compose

Docker Compose starts PostgreSQL and Adminer only. The FastAPI server is run locally as shown above.

```bash
# Build and start the database containers
docker-compose up --build
```

**Services & Ports:**
- **PostgreSQL Database:** localhost:5433
- **Adminer (DB UI):** http://localhost:8080
- **Database Name:** `tripsync_db`
- **Database User:** `postgres`
- **Database Password:** `<postgres-password>` (see `docker-compose.yml` / your `.env`)

---

## 📂 Project Structure

```
backend/
 ├── alembic.ini      # Alembic configuration
 ├── migrations/      # Alembic environment and revisions
 └── app/
     ├── core/        # Core configs/utilities
     ├── db/          # Database setup
     ├── models/      # SQLAlchemy models
     ├── routes/      # API routes
     ├── schemas/     # Pydantic schemas
     ├── services/    # Business logic
     ├── main.py      # Entry point (FastAPI app)
     └── router.py    # Centralized router
```

---

## ⚡ API Documentation

FastAPI auto-generates interactive docs:
- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

---

## Demo data

`scripts/seed_demo.py` creates two demonstration accounts, "Demo Rider A (demo)" and "Demo Rider B (demo)", with fictional data (example.test emails, 1000000000x phone numbers). They are not real people.

The seed writes the accounts directly as verified adults, so they can sign in even though no
college accepts example.test addresses at registration. Run `alembic upgrade head` first on
PostgreSQL (the seed creates tables itself only when `DB_AUTO_CREATE` is on).

Run from `backend/`. The password must come from the `DEMO_PASSWORD` environment variable (at least 8 characters):

```bash
DEMO_PASSWORD=... python -m scripts.seed_demo           # create or update the demo accounts (idempotent)
DEMO_PASSWORD=... python -m scripts.seed_demo --reset   # delete only the demo users' chat and pooling data
```

`--reset` never drops tables. It ends a non-demo partner's legacy pooling request
when removing their shared demo ride, and releases a non-demo campus party
partner's request. Unrelated users' data stays unchanged.

---

## Campus scheduling (shared-taxi parties)

Two students can agree to share one taxi between a campus point and a hub. The endpoints live under `/api/campus`. A party is a participant agreement, not a booking, dispatch or safety guarantee. The state machines, eligibility rule, endpoint and error reference, reconciliation protocol and concurrency notes are in [docs/campus-scheduling.md](../docs/campus-scheduling.md).

The campus tests run offline on SQLite. The Postgres concurrency tests are opt-in (run from `backend/`):

```bash
python -m pytest -q tests/test_campus_*.py
TRIPSYNC_TEST_PG_URL='postgresql+psycopg2://<user>:<password>@127.0.0.1:55432/<db>' \
  python -m pytest -q tests/test_campus_party_postgres.py
```

---

## 📋 Prerequisites

- **Python 3.10+** (the code uses `X | None` annotations)
- **PostgreSQL** (via Docker Compose, or a local install)
- **Docker & Docker Compose** (optional, for the database containers)

---

## 🛠️ Development Commands

```bash
# Install runtime and test dependencies
pip install -r requirements-dev.txt

# Run tests (from backend/)
python -m pytest -q
```

The tests run offline on an in-memory SQLite database. They need no running Postgres and no Ola Maps key.

CI also starts a disposable PostgreSQL 15 service and runs the opt-in concurrency
tests, including `tests/test_repair_postgres.py`. Locally, point
`TRIPSYNC_TEST_PG_URL` at a disposable database to enable these cases. Each test
creates and drops only its own temporary schema.

Registration accepts passwords of 8 or more characters and up to 72 UTF-8 bytes (the bcrypt
limit). Other passwords return 422 `weak_password` on registration; longer ones fail login with 401.

The tests use an in-memory email fake (read sent codes from the `sent_emails` fixture), run
with rate limits off (tests in `tests/test_rate_limit.py` turn them on), and check that
`alembic upgrade head` builds exactly the models' schema (`tests/test_migrations.py`, also on
PostgreSQL in CI).

Anonymous service posts return `poster: null`; their `poster_user_id` is also
null for public reads and other users. An authenticated owner retains their own
ID for management controls. Public named posts retain their poster information.

The frontend keeps the pooling socket open after approval and reconciles via
`GET /api/pool/requests/current` on screen focus, app resume and every five seconds
while foregrounded. Run its offline regression tests from `frontend/` with
`npm ci --ignore-scripts` followed by `npm test`.

---

## 🧪 API notes

- **Chat start and send** (`GET /api/chat/conversations/find-or-create`, `POST /api/chat/messages`) require an active approved ride with the partner: 400 for yourself, 404 for an unknown user, 403 without an active ride.
- **Conversation list** (`GET /api/chat/conversations`) lists only your conversations. The partner's `phone_number`, `email`, `year_of_study`, and `bio` are null unless the ride is active.
- **Message history and read receipts** (`GET /api/chat/messages/{id}`, `POST /api/chat/messages/{id}/read`) require conversation membership: 404 if the conversation is missing, 403 for a non-member. Members can still read history after a ride ends.
- **Socket relays** (`/api/ws/pool`, `/api/ws/chat`) refuse unauthorized `chat_message` frames with `{"type": "error", "code": "not_authorized", ...}` and malformed frames with `code: "invalid_message"`.
- **Map / route** (`POST /api/map/route`) returns 502 or 504 when the routing provider fails, and 429 when rate limited.
- **Pool requests** (`POST /api/pool/requests`) return 502 or 504 when the matching provider fails, and 409 while a ride is active.
- **Current pool request** (`GET /api/pool/requests/current`) is for state recovery after a reload. Its fields are `request`, `connection`, and `ride_ended`.
- **WebSockets** (`/api/ws/chat`, `/api/ws/pool`) authenticate with the subprotocols `['token', <jwt>]`. The server may send error frames of the form `{"type": "error", "code": ..., "detail": ...}`.
- The debug endpoint `/map/debug/ola-test` has been removed.

---

## 🌐 Port Configuration

| Service | Port | Description |
|---------|------|-------------|
| FastAPI Backend | 8000 | Main API server (run locally) |
| PostgreSQL Database | 5433 | Database connection |
| Adminer | 8080 | Database web UI (Docker Compose) |

> **Note:** Database port 5433 is used instead of default 5432 to avoid conflicts with existing PostgreSQL installations.

---

## 🔗 Database Connection

The application connects to PostgreSQL using:
- **Host:** localhost
- **Port:** 5433
- **Database:** tripsync_db
- **Username:** postgres
- **Password:** `<postgres-password>` (see `docker-compose.yml` / your `.env`)

Connection string: `postgresql+psycopg2://postgres:<postgres-password>@localhost:5433/tripsync_db`
