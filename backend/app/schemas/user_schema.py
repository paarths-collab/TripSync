# backend/app/schemas/user_schema.py

# --- REMOVE THIS IMPORT ---
# import uuid
from pydantic import BaseModel, EmailStr, field_validator

# --- College Schemas ---
class CollegeBase(BaseModel):
    name: str

class CollegeCreate(CollegeBase):
    pass

class College(CollegeBase):
    # --- CHANGE THIS LINE ---
    id: int
    # ----------------------

    class Config:
        from_attributes = True

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: str

class UserCreate(UserBase):
    password: str
    college_name: str

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value

class User(UserBase):
    # --- CHANGE THESE TWO LINES ---
    id: int
    college_id: int
    # ----------------------------

    class Config:
        from_attributes = True
