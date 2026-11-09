# backend/app/models/profile_model.py

from sqlalchemy import JSON, Column, LargeBinary, String, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base

# JSONB on PostgreSQL (as before), plain JSON elsewhere so SQLite can create and
# migrate the table without a custom compiler.
PortableJSONB = JSON().with_variant(JSONB(), "postgresql")

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    username = Column(String, unique=True, index=True, nullable=True)
    
    # --- ADDED YOUR REQUESTED FIELDS ---
    phone_number = Column(String, nullable=True)
    
    # Using Text for a potentially long biography
    bio = Column(Text, nullable=True) 
    
    year_of_study = Column(String, nullable=True)
    
    # Using JSONB is perfect for storing lists of reviews or key-value preferences.
    # It's flexible and you don't need to define the exact structure in advance.
    # For example: {"communication": 5, "punctuality": 4}
    reviews = Column(PortableJSONB, nullable=True)
    
    # For example: {"allow_smoking": false, "preferred_music": "pop"}
    preferences = Column(PortableJSONB, nullable=True)


    # You also mentioned Social Media and Emergency Contact. Let's add those too.
    # For example: {"linkedin": "url", "twitter": "url"}
    social_media_links = Column(PortableJSONB, nullable=True)
    
    # For example: {"name": "Jane Doe", "phone": "1234567890"}
    emergency_contact = Column(PortableJSONB, nullable=True)
    # ------------------------------------
    
    user = relationship("User", back_populates="profile")