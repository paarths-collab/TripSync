# backend/app/schemas/service_schema.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.service_model import ServiceStatus, CompensationType, ApplicationStatus

# --- Sub-Schemas for nested objects ---

class ProfileBase(BaseModel):
    id: int
    full_name: str
    class Config:
        from_attributes = True

class Tag(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True

# --- THIS IS THE NEW SUB-SCHEMA ---
# A minimal representation of a service post, used within an application response.
class ServicePostInfo(BaseModel):
    id: int
    title: str
    class Config:
        from_attributes = True

# --- Input Schemas (Data from Frontend) ---

class ServicePostCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=15)
    team_size: int = Field(1, gt=0)
    deadline: Optional[datetime] = None
    compensation_type: CompensationType
    compensation_amount: Optional[float] = Field(None, ge=0)
    requires_resume: bool = False
    requires_cover_letter: bool = True
    is_anonymous: bool = False
    tags: List[str] = []

class ServiceApplicationCreate(BaseModel):
    cover_letter: Optional[str] = None
    resume_url: Optional[str] = None
    proposed_rate: Optional[float] = None

class ServiceApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus

# --- Output Schemas (Data to Frontend) ---

class ServicePostBase(BaseModel):
    id: int
    title: str
    poster_user_id: Optional[int]
    is_anonymous: bool = False
    status: ServiceStatus
    team_size: int
    deadline: Optional[datetime] = None
    compensation_type: CompensationType
    compensation_amount: Optional[float] = None
    created_at: datetime
    poster: Optional[ProfileBase] = None
    tags: List[Tag] = []
    class Config:
        from_attributes = True

class ServicePostList(ServicePostBase):
    pass

class ServicePostDetail(ServicePostBase):
    description: str
    requires_resume: bool
    requires_cover_letter: bool

# --- MODIFIED: The ServiceApplication schema now correctly includes the nested post ---
class ServiceApplication(BaseModel):
    id: int
    status: ApplicationStatus
    cover_letter: Optional[str] = None
    resume_url: Optional[str] = None
    proposed_rate: Optional[float] = None
    application_date: datetime
    applicant: ProfileBase
    # --- THIS IS THE FIX ---
    service_post: ServicePostInfo  # Expect the nested service post info

    class Config:
        from_attributes = True
