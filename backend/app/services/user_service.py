# backend/app/services/user_service.py

import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import user_model
from app.schemas import user_schema

# Predefined list of colleges
ALLOWED_COLLEGES = [
    "DJSCE",
    "SPIT",
    "VJTI",
    "KJ SOMAIYA COLLEGE OF ENGINEERING",
    "THAKUR COLLEGE OF ENGINEERING",
    "ST. FRANCIS COLLEGE OF ENGINEERING"
]


# --- ADD THIS NEW FUNCTION ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a plain text password matches a hashed password."""
    encoded = plain_password.encode('utf-8')
    if len(encoded) > 72:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode('utf-8'))
    except ValueError:
        return False

def get_user_by_email(db: Session, email: str):
    """Fetches a user from the database by their email address."""
    return db.query(user_model.User).filter(user_model.User.email == email).first()


def get_or_create_college(db: Session, college_name: str):
    """
    Fetches a college by name from the database.
    If it doesn't exist, it creates a new one.
    """
    college = db.query(user_model.College).filter(user_model.College.name == college_name).first()
    if not college:
        college = user_model.College(name=college_name)
        db.add(college)
        db.commit()
        db.refresh(college)
    return college


def create_user(db: Session, user: user_schema.UserCreate):
    """Creates a new user in the database."""
    # Validate college name
    if user.college_name not in ALLOWED_COLLEGES:
        raise HTTPException(status_code=422, detail="Invalid college name")
    
    # Hash the password using bcrypt directly
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Find or create the college for the user
    college = get_or_create_college(db, college_name=user.college_name)

    # Create a new User database model instance
    db_user = user_model.User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        college_id=college.id
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
