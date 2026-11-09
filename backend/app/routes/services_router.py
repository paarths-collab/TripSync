# backend/app/routes/services_router.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import get_db
from app.services import service_service, auth_service
from app.schemas import service_schema
from app.models import user_model

router = APIRouter()

@router.post("", response_model=service_schema.ServicePostDetail, status_code=status.HTTP_201_CREATED)
def create_new_service_post(
    post_data: service_schema.ServicePostCreate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Creates a new service post. The service function handles all logic.
    The response model automatically serializes the new post object correctly.
    """
    # --- THIS IS THE FIX ---
    # The old code that caused the crash by referencing 'new_post.requirements'
    # and 'new_post.filters' has been removed. We now simply create the post and return it.
    new_post = service_service.create_service_post(db=db, user=current_user, post_data=post_data)
    return new_post

@router.get("", response_model=List[service_schema.ServicePostList])
def get_all_open_service_posts(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_optional_user),
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    tags: Optional[List[str]] = Query(None)
):
    posts = service_service.get_all_service_posts(
        db=db, skip=skip, limit=limit, search=search, tags=tags,
        viewer_id=current_user.id if current_user else None,
    )
    return posts

@router.get("/{post_id}", response_model=service_schema.ServicePostDetail)
def get_single_service_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_optional_user),
):
    """
    Fetches a single service post. The response model handles serialization.
    """
    post = service_service.get_service_post_by_id(
        db=db, post_id=post_id, viewer_id=current_user.id if current_user else None,
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service post not found")
    # --- THIS IS THE FIX ---
    # The old code that processed requirements/filters has been removed.
    return post

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_service_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    service_service.delete_service_post(db=db, post_id=post_id, user=current_user)
    return

# --- APPLICATION ENDPOINTS (UNCHANGED) ---

@router.post("/{post_id}/apply", response_model=service_schema.ServiceApplication)
def apply_for_service(
    post_id: int,
    app_data: service_schema.ServiceApplicationCreate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    new_application = service_service.create_application_for_post(
        db=db, post_id=post_id, user=current_user, app_data=app_data
    )
    return new_application

@router.get("/{post_id}/applications", response_model=List[service_schema.ServiceApplication])
def get_post_applications(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    applications = service_service.get_applications_for_post(db=db, post_id=post_id, user=current_user)
    return applications

@router.put("/applications/{application_id}", response_model=service_schema.ServiceApplication)
def update_application(
    application_id: int,
    update_data: service_schema.ServiceApplicationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    updated_application = service_service.update_application_status(
        db=db, application_id=application_id, user=current_user, update_data=update_data
    )
    return updated_application
