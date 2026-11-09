# backend/app/routes/health_router.py

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ping")
def ping_pong():
    """Liveness: the process is up (no dependencies checked)."""
    return {"ping": "pong!"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    """Readiness: 200 when the database answers SELECT 1, else 503."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any database failure means "not ready"
        logger.error("Readiness check: database unavailable (%s)", type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return {"status": "ok", "database": "ok"}
