# backend/app/schemas/user_schema.py

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _strip_lower(value):
    return value.strip().lower() if isinstance(value, str) else value


# --- College Schemas ---
class CollegeBase(BaseModel):
    name: str


class CollegeCreate(CollegeBase):
    pass


class College(CollegeBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CollegeOption(BaseModel):
    """GET /auth/colleges item."""
    id: int
    name: str
    email_domains: List[str]

    model_config = ConfigDict(from_attributes=True)


# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class User(UserBase):
    id: int
    college_id: int

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    """POST /auth/register. Password and date-of-birth rules are checked in the
    service so they answer with the coded 422 errors of the API contract."""
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=1024)
    college_id: Optional[int] = None
    # Legacy clients send the college name instead of its id.
    college_name: Optional[str] = Field(default=None, max_length=200)
    date_of_birth: Optional[str] = Field(default=None, max_length=32)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value):
        return _strip_lower(value)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class VerificationStatus(BaseModel):
    sent: bool
    resend_after_seconds: int


class RegisterResponse(BaseModel):
    id: int
    email: str
    full_name: str
    email_verified: bool
    verification: VerificationStatus


class EmailRequest(BaseModel):
    """Body with just an email. Not validated as an address: these endpoints
    answer the same for every input so they cannot be used to probe accounts."""
    email: str = Field(min_length=1, max_length=320)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value):
        return _strip_lower(value)


class SentResponse(BaseModel):
    sent: bool


class CodeSentResponse(BaseModel):
    sent: bool
    resend_after_seconds: int


class VerifyEmailConfirm(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(min_length=1, max_length=32)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value):
        return _strip_lower(value)


class PasswordReset(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(min_length=1, max_length=32)
    new_password: str = Field(max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value):
        return _strip_lower(value)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class OkResponse(BaseModel):
    ok: bool
