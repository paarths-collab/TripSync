# backend/app/schemas/profile_schema.py

from datetime import date

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any

# This will be the main schema for returning a user's full profile details.
class Profile(BaseModel):
    # User details (will be populated from the related User object)
    id: int
    full_name: str
    email: str
    email_verified: bool = False
    # Serialised as "YYYY-MM-DD"; null for accounts created before it was collected.
    date_of_birth: Optional[date] = None
    college_name: str

    # Profile details
    username: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    year_of_study: Optional[str] = None
    
    # We expect these to be dictionaries (JSON objects)
    reviews: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    social_media_links: Optional[Dict[str, Any]] = None
    emergency_contact: Optional[Dict[str, Any]] = None

    # We won't return the large resume file, but we'll indicate if it exists
    has_resume: bool = False

    class Config:
        from_attributes = True # Allows creating this schema from ORM objects


# This schema defines the fields a user is allowed to update.
# All fields are optional, so the user can update just one thing at a time.
class ProfileUpdate(BaseModel):
    
    username: Optional[str] = Field(None, max_length=50) 
    full_name: Optional[str] = Field(None, min_length=1, max_length=100) # User can update their name
    phone_number: Optional[str] = None
    bio: Optional[str] = Field(None, max_length=500)
    year_of_study: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    social_media_links: Optional[Dict[str, Any]] = None
    emergency_contact: Optional[Dict[str, Any]] = None