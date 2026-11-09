# backend/app/main.py
from fastapi import FastAPI
from app.router import router
from app.core.config import settings
from app.db.database import engine
from app.db import database as db_module
from app.db import schema as db_schema
from app.services import campus_outbox, college_service
from contextlib import asynccontextmanager
import asyncio
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from app.models import load_all_models
import logging
from logging.handlers import RotatingFileHandler
import os
from app.core.log_redaction import RedactSecretsFilter

load_dotenv()

# Configure logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# Create formatters
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# File handler for all logs
file_handler = RotatingFileHandler(
    os.path.join(log_dir, "app.log"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# File handler for errors only
error_handler = RotatingFileHandler(
    os.path.join(log_dir, "error.log"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, error_handler]
)

# Also add console handler for development
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# httpx/httpcore log full request URLs (including ?api_key=...) at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Scrub API keys from every record written by any handler configured here.
for _handler in (file_handler, error_handler, console_handler):
    _handler.addFilter(RedactSecretsFilter())
load_all_models()


def create_db_and_tables():
    """Development convenience: create missing tables (see app.db.schema)."""
    db_schema.auto_create_schema(engine)


def prepare_database() -> None:
    """Startup database work: optional create_all, then upsert the college list."""
    if settings.db_auto_create:
        create_db_and_tables()
        logger.info("Database tables created (DB_AUTO_CREATE)")
    else:
        logger.info("DB_AUTO_CREATE is off; expecting `alembic upgrade head` to have run")
    try:
        db = db_module.SessionLocal()
        try:
            college_service.sync_colleges(db)
        finally:
            db.close()
    except Exception:
        logger.exception("Could not sync colleges; is the database migrated (alembic upgrade head)?")


def cors_options(allow_origins: str) -> dict:
    """CORSMiddleware options from ALLOW_ORIGINS ("*" or a comma-separated list).

    With "*" credentials are disabled (browsers reject a wildcard with credentials,
    and the API authenticates with bearer tokens, not cookies).
    """
    origins = [o.strip() for o in (allow_origins or "").split(",") if o.strip()]
    wildcard = "*" in origins
    return {
        "allow_origins": ["*"] if wildcard else origins,
        "allow_credentials": not wildcard and bool(origins),
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }

# --- Outbox poller -----------------------------------------------------------
# Retries party-event pushes that could not be delivered at commit time. It is
# only an accelerator (clients reconcile via REST), so it swallows every error.
OUTBOX_POLL_DEFAULT_SECONDS = 5.0
logger = logging.getLogger(__name__)


def outbox_poll_seconds() -> float:
    """Poll interval from env OUTBOX_POLL_SECONDS (0 or negative disables)."""
    raw = os.getenv("OUTBOX_POLL_SECONDS")
    if raw is None or not raw.strip():
        return OUTBOX_POLL_DEFAULT_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning("Ignoring invalid OUTBOX_POLL_SECONDS; using %ss", OUTBOX_POLL_DEFAULT_SECONDS)
        return OUTBOX_POLL_DEFAULT_SECONDS


async def outbox_poll_once() -> None:
    """One poll pass: dispatch due outbox rows with a short-lived session. Never raises
    (except CancelledError)."""
    try:
        db = db_module.SessionLocal()
        try:
            await campus_outbox.dispatch_pending(db)
        finally:
            db.close()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Outbox poll failed")


async def run_outbox_poller(interval: float) -> None:
    """Every ``interval`` seconds run one poll pass."""
    while True:
        await asyncio.sleep(interval)
        await outbox_poll_once()


# This is a "lifespan" event handler.
# The code within this "startup" event will run once, before the app starts receiving requests.
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    prepare_database()
    poller = None
    interval = outbox_poll_seconds()
    if interval > 0:
        poller = asyncio.create_task(run_outbox_poller(interval))
    try:
        yield
    finally:
        if poller is not None:
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass
        logger.info("Shutting down...")

# Create the FastAPI app instance with the lifespan event handler
app = FastAPI(title=f"{settings.APP_NAME} API", lifespan=lifespan)

app.add_middleware(CORSMiddleware, **cors_options(settings.ALLOW_ORIGINS))
# Include the main router
app.include_router(router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": f"{settings.APP_NAME} API is running!"}