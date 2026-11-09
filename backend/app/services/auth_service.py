# backend/app/services/auth_service.py
"""JWT access tokens.

Claims: "sub" = str(user.id), "tv" = user.token_version, "exp". A token is
accepted only while the user exists, is active and still has the same
token_version, so bumping token_version (password reset/change) revokes every
token issued before. Tokens from before this scheme (sub = email) are rejected.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models import user_model

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def create_access_token(data: dict) -> str:
    """Low-level: sign ``data`` plus an expiry. Prefer create_token_for_user."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_token_for_user(user: user_model.User) -> str:
    return create_access_token({"sub": str(user.id), "tv": int(user.token_version or 0)})


def token_response(user: user_model.User) -> dict:
    return {"access_token": create_token_for_user(user), "token_type": "bearer"}


def user_from_token(token: str | None, db: Session) -> user_model.User | None:
    """The active user a token belongs to, or None if the token is invalid or revoked."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    version = payload.get("tv")
    if not isinstance(sub, str) or not (sub.isascii() and sub.isdigit()):
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    user = db.get(user_model.User, int(sub))
    if user is None or not user.is_active or int(user.token_version or 0) != version:
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    token: str | None = Depends(optional_oauth2_scheme), db: Session = Depends(get_db)
):
    return get_current_user(token, db) if token is not None else None


async def get_current_user_from_token(
    websocket: WebSocket,
    db: Session = Depends(get_db)
) -> user_model.User | None:
    """
    Authenticates a user for a WebSocket connection.
    Reads the token from the 'token' subprotocol: ['token', <jwt>].
    """
    try:
        token_protocol, token = websocket.scope['subprotocols']
    except (ValueError, KeyError, TypeError):
        return None
    if token_protocol != 'token' or not token:
        return None
    return user_from_token(token, db)
