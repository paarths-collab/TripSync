# TripSync Backend

Backend service for **TripSync**, built with **FastAPI** and **Uvicorn**.
The API runs locally with Uvicorn. Docker Compose starts only PostgreSQL and Adminer.

---

## 🔧 Environment Setup

Copy the template and fill in your values:

```bash
cp .env.example .env
```

`backend/.env.example` lists every variable the app reads, with placeholder values.
Never commit `.env`.

Create a `.env` file in the `TripSync/backend/` directory (values shown are placeholders):

```bash
# TripSync/backend/.env

# Variables for Docker Compose
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<postgres-password>
POSTGRES_DB=tripsync_db
POSTGRES_PORT=5433

# Variables for the FastAPI application
DATABASE_URL="postgresql://postgres:<postgres-password>@localhost:5433/tripsync_db"
ALLOW_ORIGINS="*"
```

Use the Postgres password configured in `docker-compose.yml` / your `.env`. `<postgres-password>` is a placeholder; replace it with that value.

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

- **Chat endpoints** (`/api/chat/...`, `/api/ws/chat`) require an approved, active ride. Otherwise they return 403.
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

Connection string: `postgresql://postgres:<postgres-password>@localhost:5433/tripsync_db`
