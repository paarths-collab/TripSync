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

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Server will run at:** 👉 http://localhost:8000

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

Run from `backend/`. The password must come from the `DEMO_PASSWORD` environment variable (at least 8 characters):

```bash
DEMO_PASSWORD=... python -m scripts.seed_demo           # create or update the demo accounts (idempotent)
DEMO_PASSWORD=... python -m scripts.seed_demo --reset   # delete only the demo users' chat and pooling data
```

`--reset` never drops tables and leaves other users' data alone.

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

---

## 🧪 API notes

- **Chat start and send** (`GET /api/chat/conversations/find-or-create`, `POST /api/chat/messages`) require an active approved ride with the partner: 400 for yourself, 404 for an unknown user, 403 without an active ride.
- **Conversation list** (`GET /api/chat/conversations`) lists only your conversations. The partner's `phone_number`, `email`, `year_of_study`, and `bio` are null unless the ride is active.
- **Message history and read receipts** (`GET /api/chat/messages/{id}`, `POST /api/chat/messages/{id}/read`) require conversation membership: 404 if the conversation is missing, 403 for a non-member. Members can still read history after a ride ends.
- **Socket relays** (`/api/ws/pool`, `/api/ws/chat`) refuse unauthorized `chat_message` frames with `{"type": "error", "code": "not_authorized", ...}` and malformed frames with `code: "invalid_message"`.
- **Map / route** (`POST /api/map/route`) returns 502 or 504 when the routing provider fails.
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
