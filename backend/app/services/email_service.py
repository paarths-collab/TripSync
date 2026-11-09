# backend/app/services/email_service.py
"""Outgoing email behind a small EmailSender interface.

Backends (EMAIL_BACKEND):
- console (default): writes "Verification code for <masked email>: <code>" to
  the server log at WARNING so a developer can sign up locally without SMTP.
  Never use it in production: anyone who can read the logs can read the codes.
- smtp: stdlib smtplib with STARTTLS, configured by SMTP_HOST / SMTP_PORT /
  SMTP_USER / SMTP_PASSWORD / EMAIL_FROM. Codes are never logged.
Tests install MemoryEmailSender with set_email_sender() and read .messages.

Callers send AFTER their database transaction has committed (FastAPI background
tasks), and send failures are logged without the code and never reported to the
client, so the HTTP response does not reveal whether an account exists.
"""

import logging
import smtplib
import ssl
import threading
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from typing import Optional, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

PURPOSE_VERIFY = "VERIFY"
PURPOSE_RESET = "RESET"


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str
    # Set for code emails so the console backend and test fakes can read it.
    code: Optional[str] = None
    purpose: Optional[str] = None
    headers: dict = field(default_factory=dict)


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


def mask_email(email: str) -> str:
    """'student@djsce.ac.in' -> 's***@djsce.ac.in'."""
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    return f"{local[:1]}***@{domain}"


class ConsoleEmailSender:
    """Development backend: logs code emails instead of sending them."""

    def send(self, message: OutgoingEmail) -> None:
        if message.code is not None:
            label = "password reset" if message.purpose == PURPOSE_RESET else "email verification"
            logger.warning(
                "Verification code for %s: %s (%s; EMAIL_BACKEND=console, not sent)",
                mask_email(message.to), message.code, label,
            )
        else:
            logger.warning("Email to %s not sent (EMAIL_BACKEND=console): %s",
                           mask_email(message.to), message.subject)


class SmtpEmailSender:
    """Sends mail over SMTP with STARTTLS. Never logs message bodies or codes."""

    def __init__(self, host: str, port: int, username: Optional[str], password: Optional[str],
                 sender: str, starttls: bool = True, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.starttls = starttls
        self.timeout = timeout

    def send(self, message: OutgoingEmail) -> None:
        mime = MimeMessage()
        mime["From"] = self.sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        for name, value in message.headers.items():
            mime[name] = value
        mime.set_content(message.body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            smtp.ehlo()
            if self.starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(mime)
        logger.info("Sent %s email to %s", (message.purpose or "notification").lower(), mask_email(message.to))


class MemoryEmailSender:
    """Test fake: keeps every message in memory."""

    def __init__(self):
        self.messages: list[OutgoingEmail] = []
        self.fail = False

    def send(self, message: OutgoingEmail) -> None:
        if self.fail:
            raise ConnectionError("simulated email failure")
        self.messages.append(message)

    def codes_for(self, email: str, purpose: Optional[str] = None) -> list[str]:
        return [m.code for m in self.messages
                if m.to == email and m.code is not None and (purpose is None or m.purpose == purpose)]

    def last_code(self, email: str, purpose: Optional[str] = None) -> Optional[str]:
        codes = self.codes_for(email, purpose)
        return codes[-1] if codes else None


_override: Optional[EmailSender] = None
_lock = threading.Lock()


def set_email_sender(sender: Optional[EmailSender]) -> None:
    """Install a sender (tests); None restores the configured backend."""
    global _override
    with _lock:
        _override = sender


def build_sender_from_settings() -> EmailSender:
    if settings.EMAIL_BACKEND == "smtp":
        if not settings.SMTP_HOST or not settings.EMAIL_FROM:
            raise RuntimeError("EMAIL_BACKEND=smtp needs SMTP_HOST and EMAIL_FROM")
        return SmtpEmailSender(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            sender=settings.EMAIL_FROM,
            starttls=settings.SMTP_STARTTLS,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )
    return ConsoleEmailSender()


def get_email_sender() -> EmailSender:
    with _lock:
        if _override is not None:
            return _override
    return build_sender_from_settings()


def code_email(to: str, code: str, purpose: str, ttl_minutes: int) -> OutgoingEmail:
    app = settings.APP_NAME
    if purpose == PURPOSE_RESET:
        subject = f"Your {app} password reset code"
        intro = f"Use this code to reset your {app} password:"
    else:
        subject = f"Your {app} verification code"
        intro = f"Use this code to verify your email address for {app}:"
    body = (
        f"{intro}\n\n    {code}\n\n"
        f"The code expires in {ttl_minutes} minutes. If you did not ask for it, you can ignore this email.\n"
    )
    return OutgoingEmail(to=to, subject=subject, body=body, code=code, purpose=purpose)


def send_code_email(to: str, code: str, purpose: str, ttl_minutes: int) -> bool:
    """Send a code email. Returns False (and logs without the code) on any failure."""
    try:
        get_email_sender().send(code_email(to, code, purpose, ttl_minutes))
        return True
    except Exception as exc:  # noqa: BLE001 - delivery failures must never reach the client
        logger.error("Could not send %s email to %s (%s)", purpose.lower(), mask_email(to), type(exc).__name__)
        return False
