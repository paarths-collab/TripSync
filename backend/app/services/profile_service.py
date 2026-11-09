from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models import user_model, profile_model
from app.schemas import profile_schema

def get_user_profile(db: Session, user: user_model.User) -> dict:
    """
    Fetches a user's profile and constructs a dictionary that perfectly
    matches the profile_schema.Profile Pydantic model.
    """
    user_with_details = db.query(user_model.User).options(
        joinedload(user_model.User.profile),
        joinedload(user_model.User.college)
    ).filter(user_model.User.id == user.id).first()

    if not user_with_details:
        raise HTTPException(status_code=404, detail="User not found")

    if not user_with_details.profile:
        new_profile = profile_model.Profile(user_id=user.id)
        db.add(new_profile)
        db.commit()
        db.refresh(user_with_details)

    # --- THIS IS THE CRITICAL FIX ---
    # We manually construct a dictionary to ensure all fields, including
    # the nested 'college_name', are present before Pydantic validation.
    profile_data = {
        "id": user_with_details.id,
        "full_name": user_with_details.full_name,
        "email": user_with_details.email,
        "email_verified": user_with_details.email_verified_at is not None,
        "date_of_birth": user_with_details.date_of_birth,
        "college_name": user_with_details.college.name if user_with_details.college else "N/A",
        "username": user_with_details.profile.username,
        "phone_number": user_with_details.profile.phone_number,
        "bio": user_with_details.profile.bio,
        "year_of_study": user_with_details.profile.year_of_study,
        "reviews": user_with_details.profile.reviews,
        "preferences": user_with_details.profile.preferences,
        "social_media_links": user_with_details.profile.social_media_links,
        "emergency_contact": user_with_details.profile.emergency_contact,
        "has_resume": False # Placeholder for now
    }
    return profile_data


def update_user_profile(db: Session, user: user_model.User, profile_data: profile_schema.ProfileUpdate) -> dict:
    """
    Updates a user's profile with the provided data.
    """
    user_profile = user.profile
    if not user_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = profile_data.model_dump(exclude_unset=True)

    if "full_name" in update_data:
        user.full_name = update_data.pop("full_name")

    for key, value in update_data.items():
        setattr(user_profile, key, value)
    
    db.add(user)
    db.add(user_profile)
    db.commit()
    db.refresh(user)
    
    # Return the newly updated, combined profile
    return get_user_profile(db=db, user=user)