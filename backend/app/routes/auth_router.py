# backend/app/routes/auth_router.py
"""Authentication: colleges, registration, email verification, login, passwords.

Every endpoint except the legacy OAuth2 form login (/token) answers errors as
{"detail": {"code", "message"}}. Code emails are sent by background tasks, i.e.
after the response's database work has committed, and their outcome is never
reported to the caller.
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.errors import CodedErrorRoute, api_error
from app.db.database import get_db
from app.models import user_model
from app.models.email_code_model import EmailCodePurpose
from app.schemas import token_schema, user_schema
from app.services import auth_service, college_service, email_code_service, email_service, user_service

router = APIRouter()
# Routes added with the coded error shape (including for request-validation errors).
coded = APIRouter(route_class=CodedErrorRoute)

CODE_TTL_MINUTES = email_code_service.CODE_TTL_SECONDS // 60
RESEND_SECONDS = email_code_service.RESEND_COOLDOWN_SECONDS


def _send_code_later(background: BackgroundTasks, email: str, code: str, purpose: EmailCodePurpose) -> None:
    background.add_task(email_service.send_code_email, email, code, purpose.value, CODE_TTL_MINUTES)


# --------------------------------------------------------------------------
# Colleges
# --------------------------------------------------------------------------
@coded.get("/colleges", response_model=List[user_schema.CollegeOption])
def list_colleges(db: Session = Depends(get_db)):
    """Colleges open for registration, with the email domains each accepts."""
    return [
        user_schema.CollegeOption(id=c.id, name=c.name, email_domains=list(c.email_domains or []))
        for c in college_service.open_colleges(db)
    ]


# --------------------------------------------------------------------------
# Registration and email verification
# --------------------------------------------------------------------------
@coded.post(
    "/register",
    response_model=user_schema.RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit.limit_by_ip("register_ip"))],
)
def register_user(
    body: user_schema.RegisterRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create an unverified account and email it a 6-digit verification code."""
    user = user_service.register_user(
        db,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        college_id=body.college_id,
        college_name=body.college_name,
        date_of_birth=body.date_of_birth,
    )
    code = email_code_service.issue_code(db, user, EmailCodePurpose.VERIFY)
    email_code_service.start_cooldown(EmailCodePurpose.VERIFY.value, user.email)
    _send_code_later(background, user.email, code, EmailCodePurpose.VERIFY)
    return user_schema.RegisterResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=False,
        verification=user_schema.VerificationStatus(sent=True, resend_after_seconds=RESEND_SECONDS),
    )


@coded.post(
    "/verify-email/request",
    response_model=user_schema.CodeSentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit.limit_by_ip("verify_request_ip"))],
)
def request_verification_code(
    body: user_schema.EmailRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Email a new code if an unverified account exists. Same answer for every address."""
    email = body.email
    remaining = email_code_service.try_start_cooldown(EmailCodePurpose.VERIFY.value, email)
    if remaining > 0:
        raise rate_limit.too_many_requests(remaining)
    user = user_service.get_user_by_email(db, email)
    if user is not None and user.is_active and user.email_verified_at is None:
        code = email_code_service.issue_code(db, user, EmailCodePurpose.VERIFY)
        _send_code_later(background, user.email, code, EmailCodePurpose.VERIFY)
    return {"sent": True, "resend_after_seconds": RESEND_SECONDS}


@coded.post(
    "/verify-email/confirm",
    response_model=token_schema.Token,
    dependencies=[Depends(rate_limit.limit_by_ip("verify_confirm_ip"))],
)
def confirm_email(body: user_schema.VerifyEmailConfirm, db: Session = Depends(get_db)):
    """Confirm the address with the emailed code; logs the user in."""
    rate_limit.enforce("verify_confirm_email", body.email)
    user = user_service.get_user_by_email(db, body.email)
    user = email_code_service.consume_code(db, user, EmailCodePurpose.VERIFY, body.code)
    if user.email_verified_at is None:
        user.email_verified_at = email_code_service.utcnow()
    db.commit()
    db.refresh(user)
    return auth_service.token_response(user)


# --------------------------------------------------------------------------
# Login (legacy OAuth2 password form; 401 detail stays a string)
# --------------------------------------------------------------------------
def _login_email_limit(form_data: OAuth2PasswordRequestForm = Depends()) -> None:
    rate_limit.enforce("login_email", user_service.normalize_email(form_data.username))


@router.post(
    "/token",
    response_model=token_schema.Token,
    dependencies=[Depends(rate_limit.limit_by_ip("login_ip")), Depends(_login_email_limit)],
)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    OAuth2 password flow: form fields 'username' (the email) and 'password'.

    401 for wrong credentials or a disabled account; 403 email_not_verified when
    the password is right but the address has not been confirmed yet.
    """
    user = user_service.get_user_by_email(db, email=form_data.username)
    if user is None:
        user_service.burn_password_check(form_data.password)
    if (
        user is None
        or not user_service.verify_password(form_data.password, user.hashed_password)
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.email_verified_at is None:
        raise api_error(
            403, "email_not_verified",
            "Verify your email address to sign in. We can send you a new code.",
        )
    return auth_service.token_response(user)


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
@coded.post(
    "/password/forgot",
    response_model=user_schema.SentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit.limit_by_ip("password_forgot_ip"))],
)
def forgot_password(
    body: user_schema.EmailRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Email a reset code if the account exists. Always answers 202 {"sent": true}."""
    email = body.email
    # Within the resend cooldown nothing new is sent, silently (same answer either way).
    if email_code_service.try_start_cooldown(EmailCodePurpose.RESET.value, email) == 0:
        user = user_service.get_user_by_email(db, email)
        if user is not None and user.is_active:
            code = email_code_service.issue_code(db, user, EmailCodePurpose.RESET)
            _send_code_later(background, user.email, code, EmailCodePurpose.RESET)
    return {"sent": True}


@coded.post(
    "/password/reset",
    response_model=user_schema.OkResponse,
    dependencies=[Depends(rate_limit.limit_by_ip("password_reset_ip"))],
)
def reset_password(body: user_schema.PasswordReset, db: Session = Depends(get_db)):
    """Set a new password with an emailed reset code. Revokes every existing token."""
    rate_limit.enforce("password_reset_email", body.email)
    user_service.validate_new_password(body.new_password)
    user = user_service.get_user_by_email(db, body.email)
    user = email_code_service.consume_code(db, user, EmailCodePurpose.RESET, body.code)
    user.hashed_password = user_service.hash_password(body.new_password)
    user.token_version = int(user.token_version or 0) + 1
    if user.email_verified_at is None:
        # Receiving the reset code proves control of the address.
        user.email_verified_at = email_code_service.utcnow()
    db.commit()
    return {"ok": True}


@coded.post("/password/change", response_model=token_schema.Token)
def change_password(
    body: user_schema.PasswordChange,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """Change the password; revokes older tokens and returns a fresh one."""
    user_service.validate_new_password(body.new_password)
    if not user_service.verify_password(body.current_password, current_user.hashed_password):
        raise api_error(400, "wrong_password", "Your current password is not correct.")
    current_user.hashed_password = user_service.hash_password(body.new_password)
    current_user.token_version = int(current_user.token_version or 0) + 1
    db.commit()
    db.refresh(current_user)
    return auth_service.token_response(current_user)


router.include_router(coded)
