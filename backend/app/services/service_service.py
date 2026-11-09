# backend/app/services/service_service.py

from sqlalchemy.orm import Session, joinedload, contains_eager
from typing import List, Optional
from fastapi import HTTPException, status
from app.models import user_model, service_model
from app.schemas import service_schema

def get_or_create_tags(db: Session, tag_names: List[str]) -> List[service_model.Tag]:
    """
    Finds existing tags in the database from a list of names.
    If a tag does not exist, it creates a new one.
    """
    tags = []
    for name in tag_names:
        name_lower = name.lower().strip()
        if not name_lower:
            continue
            
        tag = db.query(service_model.Tag).filter(service_model.Tag.name == name_lower).first()
        
        if not tag:
            tag = service_model.Tag(name=name_lower)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        tags.append(tag)
    return tags

def create_service_post(
    db: Session, user: user_model.User, post_data: service_schema.ServicePostCreate
) -> service_model.ServicePost:
    """Creates a new service post and associates it with tags."""
    
    tags = get_or_create_tags(db, post_data.tags)

    new_post = service_model.ServicePost(
        poster_user_id=user.id,
        title=post_data.title,
        description=post_data.description,
        team_size=post_data.team_size,
        deadline=post_data.deadline,
        compensation_type=post_data.compensation_type,
        compensation_amount=post_data.compensation_amount,
        requires_resume=post_data.requires_resume,
        requires_cover_letter=post_data.requires_cover_letter,
        is_anonymous=post_data.is_anonymous,
        tags=tags
    )
    
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    return new_post

def get_all_service_posts(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    search: Optional[str] = None,
    tags: Optional[List[str]] = None,
    viewer_id: Optional[int] = None,
) -> List[service_schema.ServicePostList]:
    """
    Fetches a list of open service posts with optional search and tag filtering.
    """
    query = db.query(service_model.ServicePost).options(
        joinedload(service_model.ServicePost.poster),
        joinedload(service_model.ServicePost.tags)
    ).filter(
        service_model.ServicePost.status == service_model.ServiceStatus.OPEN
    )

    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            (service_model.ServicePost.title.ilike(search_term)) |
            (service_model.ServicePost.description.ilike(search_term))
        )

    if tags:
        for tag_name in tags:
            query = query.filter(service_model.ServicePost.tags.any(name=tag_name.lower().strip()))

    posts = query.order_by(
        service_model.ServicePost.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return [_post_view(post, service_schema.ServicePostList, viewer_id) for post in posts]

def _post_view(post, schema, viewer_id):
    view = schema.model_validate(post)
    if post.is_anonymous:
        view.poster = None
        if post.poster_user_id != viewer_id:
            view.poster_user_id = None
    return view


def get_service_post_by_id(
    db: Session, post_id: int, viewer_id: Optional[int] = None
) -> service_schema.ServicePostDetail | None:
    """Fetches a single, detailed service post by its ID."""
    post = db.query(service_model.ServicePost).options(
        joinedload(service_model.ServicePost.poster),
        joinedload(service_model.ServicePost.tags)
    ).filter(service_model.ServicePost.id == post_id).first()
    
    return _post_view(post, service_schema.ServicePostDetail, viewer_id) if post else None

def delete_service_post(db: Session, post_id: int, user: user_model.User):
    post_to_delete = db.query(service_model.ServicePost).filter(
        service_model.ServicePost.id == post_id
    ).first()

    if not post_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service post not found")

    if post_to_delete.poster_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post")

    db.delete(post_to_delete)
    db.commit()
    return

def create_application_for_post(
    db: Session, post_id: int, user: user_model.User, app_data: service_schema.ServiceApplicationCreate
) -> service_model.ServiceApplication:
    """Creates a new application for a service post."""
    post = db.query(service_model.ServicePost).filter(service_model.ServicePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service post not found.")
    if post.poster_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot apply to your own post.")
    
    existing_app = db.query(service_model.ServiceApplication).filter(
        service_model.ServiceApplication.service_post_id == post_id,
        service_model.ServiceApplication.applicant_user_id == user.id
    ).first()
    if existing_app:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already applied to this post.")

    new_app = service_model.ServiceApplication(
        service_post_id=post_id,
        applicant_user_id=user.id,
        **app_data.model_dump()
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return new_app

def get_applications_for_post(
    db: Session, post_id: int, user: user_model.User
) -> List[service_model.ServiceApplication]:
    """Gets all applications for a post. Only the post owner can access this."""
    post = db.query(service_model.ServicePost).filter(service_model.ServicePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service post not found.")
    if post.poster_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view applications for this post.")

    applications = db.query(service_model.ServiceApplication).options(
        joinedload(service_model.ServiceApplication.applicant)
    ).filter(
        service_model.ServiceApplication.service_post_id == post_id
    ).order_by(service_model.ServiceApplication.application_date.desc()).all()
    return applications

def update_application_status(
    db: Session, application_id: int, user: user_model.User, update_data: service_schema.ServiceApplicationStatusUpdate
) -> service_model.ServiceApplication:
    """Updates an application's status. Only the post owner can do this."""
    application = db.query(service_model.ServiceApplication).options(
        joinedload(service_model.ServiceApplication.service_post)
    ).filter(service_model.ServiceApplication.id == application_id).first()
    
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    if application.service_post.poster_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this application.")
    if update_data.status not in [service_model.ApplicationStatus.ACCEPTED, service_model.ApplicationStatus.REJECTED]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status can only be updated to 'accepted' or 'rejected'.")

    application.status = update_data.status
    
    if update_data.status == service_model.ApplicationStatus.ACCEPTED:
        application.service_post.status = service_model.ServiceStatus.IN_PROGRESS

    db.commit()
    db.refresh(application)
    return application
