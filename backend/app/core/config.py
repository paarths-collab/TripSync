# backend/app/core/config.py

from typing import Dict, List, Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # --- App -----------------------------------------------------------------
    APP_NAME: str = "TripSync"
    DATABASE_URL: str
    # Comma-separated list of allowed CORS origins, or "*" (then credentials are off).
    ALLOW_ORIGINS: str
    # Run Base.metadata.create_all at startup. None means "only for SQLite URLs";
    # Postgres deployments use `alembic upgrade head` instead.
    DB_AUTO_CREATE: Optional[bool] = None

    # --- Auth ------------------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    # JSON mapping of college name -> list of email domains, e.g.
    # {"DJSCE": ["djsce.ac.in"], "SPIT": ["spit.ac.in"]}. Colleges not listed use
    # the built-in defaults; an empty list keeps registration closed for that college.
    COLLEGE_EMAIL_DOMAINS: Dict[str, List[str]] = {}

    # --- Email -----------------------------------------------------------------
    # "console" writes verification codes to the server log (development only);
    # "smtp" sends real mail and never logs codes.
    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_STARTTLS: bool = True
    SMTP_TIMEOUT_SECONDS: float = 10.0
    EMAIL_FROM: Optional[str] = None

    # --- Rate limiting ---------------------------------------------------------
    # In-process, in-memory limits ("<count>/<seconds>"; "off" disables one rule).
    # They assume a single worker process; see README.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_IP: str = "60/300"
    RATE_LIMIT_LOGIN_EMAIL: str = "10/600"
    RATE_LIMIT_REGISTER_IP: str = "60/3600"
    RATE_LIMIT_VERIFY_REQUEST_IP: str = "60/3600"
    RATE_LIMIT_VERIFY_CONFIRM_IP: str = "60/600"
    RATE_LIMIT_VERIFY_CONFIRM_EMAIL: str = "10/600"
    RATE_LIMIT_PASSWORD_FORGOT_IP: str = "30/3600"
    RATE_LIMIT_PASSWORD_RESET_IP: str = "60/600"
    RATE_LIMIT_PASSWORD_RESET_EMAIL: str = "10/600"
    RATE_LIMIT_PLACES_USER: str = "60/60"
    RATE_LIMIT_ROUTE_USER: str = "30/60"
    RATE_LIMIT_CHAT_MESSAGE_USER: str = "30/60"
    # Only when the API sits behind a reverse proxy you control: take the client
    # address from X-Forwarded-For, TRUSTED_PROXY_HOPS entries from the right.
    TRUSTED_PROXY: bool = False
    TRUSTED_PROXY_HOPS: int = 1

    # --- Maps ------------------------------------------------------------------
    OLA_MAPS_API_KEY: str
    # Optional proxy for OLA Maps API (if carrier blocks)
    OLA_MAPS_PROXY: Optional[str] = None
    PLACES_CACHE_TTL_SECONDS: int = 600
    ROUTE_CACHE_TTL_SECONDS: int = 120
    MAPS_CACHE_MAX_ENTRIES: int = 1000

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.strip().lower().startswith("sqlite")

    @property
    def db_auto_create(self) -> bool:
        if self.DB_AUTO_CREATE is None:
            return self.is_sqlite
        return self.DB_AUTO_CREATE


settings = Settings()
