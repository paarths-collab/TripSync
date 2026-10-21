# backend/app/routes/campus_requests_router.py
"""Campus requests router: GET /landmarks, /requests (+ PATCH/DELETE) and /requests/{id}/suggestions."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import campus_time
from app.db.database import get_db
from app.models import user_model
from app.schemas import campus_schema
from app.services import auth_service, campus_request_service, campus_suggestion_service

router = APIRouter()


def _commit_and_view(db: Session, row) -> campus_schema.TravelRequestOut:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return campus_schema.TravelRequestOut.from_request(row)


@router.get("/landmarks", response_model=List[campus_schema.LandmarkOut])
def list_landmarks(
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    return campus_request_service.list_landmarks(db, current_user)


@router.post("/requests", response_model=campus_schema.TravelRequestOut, status_code=201)
def create_request(
    body: campus_schema.TravelRequestCreate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    now = campus_time.utcnow()
    try:
        row = campus_request_service.create_request(db, current_user, body, now)
    except Exception:
        db.rollback()
        raise
    return _commit_and_view(db, row)


@router.get("/requests", response_model=List[campus_schema.TravelRequestOut])
def list_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    now = campus_time.utcnow()
    campus_request_service.expire_stale(db, now)
    db.commit()
    rows = campus_request_service.list_requests(db, current_user, status)
    return [campus_schema.TravelRequestOut.from_request(r) for r in rows]


@router.get("/requests/{request_id}", response_model=campus_schema.TravelRequestOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    campus_request_service.get_own_request(db, current_user, request_id)  # 404 early
    campus_request_service.expire_stale(db, campus_time.utcnow())
    db.commit()
    row = campus_request_service.get_own_request(db, current_user, request_id)
    return campus_schema.TravelRequestOut.from_request(row)


@router.patch("/requests/{request_id}", response_model=campus_schema.TravelRequestOut)
def patch_request(
    request_id: int,
    body: campus_schema.TravelRequestPatch,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    now = campus_time.utcnow()
    try:
        row = campus_request_service.patch_request(db, current_user, request_id, body, now)
    except Exception:
        db.rollback()
        raise
    return _commit_and_view(db, row)


@router.delete("/requests/{request_id}", response_model=campus_schema.TravelRequestOut)
def delete_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    now = campus_time.utcnow()
    try:
        row = campus_request_service.cancel_request(db, current_user, request_id, now)
    except Exception:
        db.rollback()
        raise
    return _commit_and_view(db, row)


@router.get(
    "/requests/{request_id}/suggestions",
    response_model=campus_schema.SuggestionsResponse,
)
async def request_suggestions(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    now = campus_time.utcnow()
    try:
        return await campus_suggestion_service.suggestions_for_request(
            db, current_user, request_id, now
        )
    except Exception:
        db.rollback()
        raise
