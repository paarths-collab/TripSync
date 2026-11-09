"""Registration, email verification, login, password and token-revocation rules."""

import logging
import time
from datetime import date, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core import rate_limit
from app.core.config import settings
from app.core.log_redaction import RedactSecretsFilter
from app.models import user_model
from app.models.email_code_model import EmailCode
from app.services import auth_service, college_service, email_code_service, email_service, user_service

ADULT_DOB = "2000-01-01"
PASSWORD = "correct-horse-battery"
EMAIL = "new.student@djsce.ac.in"


def _register(client, college_id=None, **overrides):
    body = {"email": EMAIL, "full_name": "New Student", "password": PASSWORD, "date_of_birth": ADULT_DOB}
    if college_id is not None:
        body["college_id"] = college_id
    else:
        body["college_name"] = "DJSCE"
    body.update(overrides)
    return client.post("/api/auth/register", json=body)


def _login(client, email, password):
    return client.post("/api/auth/token", data={"username": email, "password": password})


def _confirm(client, email, code):
    return client.post("/api/auth/verify-email/confirm", json={"email": email, "code": code})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _code(detail_response):
    return detail_response.json()["detail"]["code"]


def _verified_user(client, sent_emails, college, email=EMAIL, password=PASSWORD):
    assert _register(client, college.id, email=email, password=password).status_code == 201
    response = _confirm(client, email, sent_emails.last_code(email))
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch):
    """Low bcrypt cost for speed; hashes stay valid bcrypt hashes."""
    real_gensalt = user_service.bcrypt.gensalt
    monkeypatch.setattr(user_service.bcrypt, "gensalt", lambda rounds=12, prefix=b"2b": real_gensalt(4, prefix))


class ShiftedClock:
    """time.monotonic() plus an adjustable offset (for cooldown tests)."""

    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.monotonic() + self.offset


# --------------------------------------------------------------------------
# Colleges
# --------------------------------------------------------------------------
def test_colleges_list_only_open_colleges(client, test_session_factory):
    with test_session_factory() as db:
        college_service.sync_colleges(db)
    response = client.get("/api/auth/colleges")
    assert response.status_code == 200
    body = response.json()
    assert [c["name"] for c in body] == ["DJSCE"]
    assert body[0]["email_domains"] == ["djsce.ac.in"]
    assert isinstance(body[0]["id"], int)


def test_sync_colleges_applies_setting_and_is_idempotent(test_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "COLLEGE_EMAIL_DOMAINS", {
        "spit": [" SPIT.ac.in ", "@students.spit.ac.in", "spit.ac.in"],
        "DJSCE": [],
        "Unknown College": ["unknown.example"],
    })
    with test_session_factory() as db:
        college_service.sync_colleges(db)
        college_service.sync_colleges(db)
        rows = {c.name: c.email_domains for c in db.query(user_model.College).all()}
    assert set(rows) == set(college_service.ALLOWED_COLLEGES)
    assert rows["SPIT"] == ["spit.ac.in", "students.spit.ac.in"]
    assert rows["DJSCE"] == []
    assert rows["VJTI"] == []


def test_default_domains_open_only_djsce():
    assert college_service.configured_domains()["DJSCE"] == ["djsce.ac.in"]
    others = {n: d for n, d in college_service.configured_domains().items() if n != "DJSCE"}
    assert all(domains == [] for domains in others.values())
    assert not any("example.test" in d for domains in college_service.configured_domains().values() for d in domains)


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def test_register_creates_unverified_user_and_emails_code(client, college, sent_emails, test_session_factory):
    response = _register(client, college.id, email="  New.Student@DJSCE.ac.in ")
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "email": EMAIL,
        "full_name": "New Student",
        "email_verified": False,
        "verification": {"sent": True, "resend_after_seconds": 60},
    }
    [message] = sent_emails.messages
    assert message.to == EMAIL and message.purpose == "VERIFY"
    assert len(message.code) == 6 and message.code.isdigit()
    assert message.code in message.body
    with test_session_factory() as db:
        user = db.get(user_model.User, body["id"])
        assert user.email == EMAIL
        assert user.date_of_birth == date(2000, 1, 1)
        assert user.email_verified_at is None
        assert user.token_version == 0 and user.is_active is True
        assert user.hashed_password != PASSWORD
        stored = db.query(EmailCode).one()
        # Hashed at rest (HMAC-SHA256 hex), never the code itself.
        assert stored.code_hash != message.code and len(stored.code_hash) == 64
        assert stored.code_hash == email_code_service.hash_code("VERIFY", EMAIL, message.code)
        assert stored.expires_at - stored.created_at == timedelta(minutes=10)


def test_register_accepts_legacy_college_name(client, sent_emails):
    response = _register(client, college_name="djsce")
    assert response.status_code == 201
    assert sent_emails.last_code(EMAIL) is not None


@pytest.mark.parametrize("email", ["student@gmail.com", "student@sub.djsce.ac.in", "student@djsce.ac.in.evil.example"])
def test_register_rejects_other_domains(client, college, email):
    response = _register(client, college.id, email=email)
    assert response.status_code == 422
    assert _code(response) == "email_domain_mismatch"


def test_register_closed_college(client, college, test_session_factory):
    with test_session_factory() as db:
        college_service.sync_colleges(db)
        spit = db.query(user_model.College).filter_by(name="SPIT").one()
    response = _register(client, spit.id, email="someone@spit.ac.in")
    assert response.status_code == 422
    assert _code(response) == "email_domain_mismatch"


@pytest.mark.parametrize("overrides", [
    {"college_id": 99999},
    {"college_name": "Not A College"},
    {"college_name": None},
])
def test_register_invalid_college(client, overrides):
    body = {"email": EMAIL, "full_name": "X", "password": PASSWORD, "date_of_birth": ADULT_DOB, **overrides}
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 422
    assert _code(response) == "invalid_college"


@pytest.mark.parametrize("today, dob, ok", [
    (date(2026, 6, 15), "2008-06-15", True),     # 18th birthday today
    (date(2026, 6, 15), "2008-06-16", False),    # one day short
    (date(2026, 2, 28), "2008-02-29", False),    # leap-day birthday: not yet in a common year
    (date(2026, 3, 1), "2008-02-29", True),
])
def test_register_minimum_age(client, college, monkeypatch, today, dob, ok):
    monkeypatch.setattr(user_service, "today", lambda: today)
    response = _register(client, college.id, date_of_birth=dob)
    if ok:
        assert response.status_code == 201
    else:
        assert response.status_code == 422
        assert _code(response) == "underage"


@pytest.mark.parametrize("dob", [None, "", "2000-13-01", "2000-02-30", "01/01/2000", "20000101", "2999-01-01", "1850-01-01"])
def test_register_invalid_date_of_birth(client, college, dob):
    response = _register(client, college.id, date_of_birth=dob)
    assert response.status_code == 422
    assert _code(response) == "invalid_date_of_birth"


@pytest.mark.parametrize("password", ["short7!", "x" * 73, "é" * 37])
def test_register_weak_password(client, college, password):
    response = _register(client, college.id, password=password)
    assert response.status_code == 422
    assert _code(response) == "weak_password"


def test_register_duplicate_email_any_case(client, college, sent_emails):
    assert _register(client, college.id).status_code == 201
    response = _register(client, college.id, email=EMAIL.upper())
    assert response.status_code == 409
    assert _code(response) == "email_taken"


def test_register_insert_race_returns_409(client, college, monkeypatch):
    assert _register(client, college.id).status_code == 201
    # Simulate a concurrent registration that passed the pre-check.
    monkeypatch.setattr(user_service, "get_user_by_email", lambda db, email: None)
    response = _register(client, college.id)
    assert response.status_code == 409
    assert _code(response) == "email_taken"


def test_register_bad_input_uses_coded_shape_without_echoing_values(client, college):
    response = client.post("/api/auth/register", json={
        "email": "not-an-email", "full_name": "X", "password": "secret-value-123",
        "college_id": college.id, "date_of_birth": ADULT_DOB,
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert "secret-value-123" not in response.text


# --------------------------------------------------------------------------
# Verification and login
# --------------------------------------------------------------------------
def test_login_requires_verified_email(client, college, sent_emails):
    _register(client, college.id)
    response = _login(client, EMAIL, PASSWORD)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "email_not_verified"
    # Wrong password never reveals the verification state.
    assert _login(client, EMAIL, "wrong-password-x").status_code == 401


def test_confirm_logs_in_and_marks_verified(client, college, sent_emails):
    _register(client, college.id)
    response = _confirm(client, EMAIL, sent_emails.last_code(EMAIL))
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    profile = client.get("/api/profile/me", headers=_bearer(token)).json()
    assert profile["email_verified"] is True
    assert profile["date_of_birth"] == ADULT_DOB
    assert _login(client, "  NEW.STUDENT@djsce.ac.in", PASSWORD).status_code == 200
    # Codes are single use.
    assert _code(_confirm(client, EMAIL, sent_emails.last_code(EMAIL))) == "invalid_code"


def test_confirm_wrong_code_then_attempts_exhausted(client, college, sent_emails):
    _register(client, college.id)
    code = sent_emails.last_code(EMAIL)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(email_code_service.MAX_ATTEMPTS):
        response = _confirm(client, EMAIL, wrong)
        assert response.status_code == 400
        assert _code(response) == "invalid_code"
    response = _confirm(client, EMAIL, code)
    assert response.status_code == 400
    assert _code(response) == "code_expired"


def test_malformed_code_is_not_counted(client, college, sent_emails):
    _register(client, college.id)
    for _ in range(email_code_service.MAX_ATTEMPTS + 2):
        assert _code(_confirm(client, EMAIL, "abc")) == "invalid_code"
    assert _confirm(client, EMAIL, sent_emails.last_code(EMAIL)).status_code == 200


def test_confirm_expired_code(client, college, sent_emails, monkeypatch):
    _register(client, college.id)
    later = datetime.utcnow() + timedelta(minutes=11)
    monkeypatch.setattr(email_code_service, "utcnow", lambda: later)
    response = _confirm(client, EMAIL, sent_emails.last_code(EMAIL))
    assert response.status_code == 400
    assert _code(response) == "code_expired"


def test_confirm_unknown_email_is_invalid_code(client):
    response = _confirm(client, "nobody@djsce.ac.in", "123456")
    assert response.status_code == 400
    assert _code(response) == "invalid_code"


def test_verify_request_cooldown_and_resend(client, college, sent_emails, monkeypatch):
    clock = ShiftedClock()
    monkeypatch.setattr(rate_limit.email_cooldown, "_clock", clock)
    _register(client, college.id)
    first = sent_emails.last_code(EMAIL)

    response = client.post("/api/auth/verify-email/request", json={"email": EMAIL})
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "too_many_requests"
    assert 1 <= detail["retry_after_seconds"] <= 60
    assert response.headers["Retry-After"] == str(detail["retry_after_seconds"])

    clock.offset = 61
    response = client.post("/api/auth/verify-email/request", json={"email": EMAIL.upper()})
    assert response.status_code == 202
    assert response.json() == {"sent": True, "resend_after_seconds": 60}
    second = sent_emails.last_code(EMAIL)
    assert len(sent_emails.codes_for(EMAIL)) == 2
    if second != first:
        # The newer code replaces the older one.
        assert _code(_confirm(client, EMAIL, first)) == "invalid_code"
    assert _confirm(client, EMAIL, second).status_code == 200


def test_verify_request_does_not_reveal_accounts(client, college, sent_emails, make_user):
    make_user("verified@djsce.ac.in", "Verified", college)
    for email in ("nobody@djsce.ac.in", "verified@djsce.ac.in", "not even an email"):
        response = client.post("/api/auth/verify-email/request", json={"email": email})
        assert response.status_code == 202
        assert response.json() == {"sent": True, "resend_after_seconds": 60}
        # The cooldown applies to every address alike.
        assert client.post("/api/auth/verify-email/request", json={"email": email}).status_code == 429
    assert sent_emails.messages == []


def test_send_failure_is_not_reported(client, college, sent_emails, caplog):
    sent_emails.fail = True
    caplog.set_level(logging.INFO)
    response = _register(client, college.id)
    assert response.status_code == 201
    assert response.json()["verification"]["sent"] is True
    assert client.post("/api/auth/password/forgot", json={"email": EMAIL}).status_code == 202
    assert "Could not send" in caplog.text
    assert EMAIL not in caplog.text  # masked


def test_inactive_user_cannot_log_in_or_verify(client, college, sent_emails, test_session_factory):
    token = _verified_user(client, sent_emails, college)
    with test_session_factory() as db:
        user = db.query(user_model.User).filter_by(email=EMAIL).one()
        user.is_active = False
        db.commit()
    assert _login(client, EMAIL, PASSWORD).status_code == 401
    assert client.get("/api/profile/me", headers=_bearer(token)).status_code == 401
    rate_limit.reset_all()
    assert client.post("/api/auth/password/forgot", json={"email": EMAIL}).status_code == 202
    assert sent_emails.codes_for(EMAIL, "RESET") == []


def test_legacy_mixed_case_email_still_logs_in(client, college, make_user, test_session_factory):
    user, _ = make_user("Legacy.User@Example.com", "Legacy", college)
    from tests.conftest import TEST_PASSWORD

    assert _login(client, "legacy.user@example.com", TEST_PASSWORD).status_code == 200


def test_legacy_unverified_user_must_verify_at_login(client, college, make_user, sent_emails, test_session_factory):
    from tests.conftest import TEST_PASSWORD

    user, _ = make_user("old.account@example.com", "Old Account", college)
    with test_session_factory() as db:
        db.get(user_model.User, user.id).email_verified_at = None
        db.commit()
    assert _code(_login(client, "old.account@example.com", TEST_PASSWORD)) == "email_not_verified"
    assert client.post("/api/auth/verify-email/request", json={"email": "old.account@example.com"}).status_code == 202
    code = sent_emails.last_code("old.account@example.com")
    assert _confirm(client, "old.account@example.com", code).status_code == 200
    assert _login(client, "old.account@example.com", TEST_PASSWORD).status_code == 200


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def test_forgot_is_always_202(client, college, sent_emails):
    for email in ("nobody@djsce.ac.in", "x"):
        response = client.post("/api/auth/password/forgot", json={"email": email})
        assert response.status_code == 202
        assert response.json() == {"sent": True}
    assert sent_emails.messages == []


def test_reset_password_revokes_old_tokens(client, college, sent_emails):
    old_token = _verified_user(client, sent_emails, college)
    assert client.post("/api/auth/password/forgot", json={"email": EMAIL}).status_code == 202
    code = sent_emails.last_code(EMAIL, "RESET")
    assert code is not None

    weak = client.post("/api/auth/password/reset", json={"email": EMAIL, "code": code, "new_password": "short"})
    assert weak.status_code == 422 and _code(weak) == "weak_password"
    wrong = client.post("/api/auth/password/reset", json={
        "email": EMAIL, "code": "999999" if code != "999999" else "888888", "new_password": "a-new-password"})
    assert wrong.status_code == 400 and _code(wrong) == "invalid_code"

    response = client.post("/api/auth/password/reset", json={"email": EMAIL, "code": code, "new_password": "a-new-password"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.get("/api/profile/me", headers=_bearer(old_token)).status_code == 401
    assert _login(client, EMAIL, PASSWORD).status_code == 401
    assert _login(client, EMAIL, "a-new-password").status_code == 200
    # The reset code cannot be used twice, nor as a verification code.
    again = client.post("/api/auth/password/reset", json={"email": EMAIL, "code": code, "new_password": "another-password"})
    assert _code(again) == "invalid_code"


def test_reset_password_expired_code(client, college, sent_emails, monkeypatch):
    _verified_user(client, sent_emails, college)
    client.post("/api/auth/password/forgot", json={"email": EMAIL})
    code = sent_emails.last_code(EMAIL, "RESET")
    later = datetime.utcnow() + timedelta(minutes=10, seconds=1)
    monkeypatch.setattr(email_code_service, "utcnow", lambda: later)
    response = client.post("/api/auth/password/reset", json={"email": EMAIL, "code": code, "new_password": "a-new-password"})
    assert response.status_code == 400 and _code(response) == "code_expired"


def test_reset_verifies_unverified_address(client, college, sent_emails):
    _register(client, college.id)
    rate_limit.reset_all()
    client.post("/api/auth/password/forgot", json={"email": EMAIL})
    code = sent_emails.last_code(EMAIL, "RESET")
    assert client.post("/api/auth/password/reset", json={
        "email": EMAIL, "code": code, "new_password": "a-new-password"}).status_code == 200
    assert _login(client, EMAIL, "a-new-password").status_code == 200


def test_change_password(client, college, sent_emails):
    token = _verified_user(client, sent_emails, college)
    url = "/api/auth/password/change"
    wrong = client.post(url, headers=_bearer(token), json={"current_password": "nope-nope", "new_password": "fresh-password"})
    assert wrong.status_code == 400 and _code(wrong) == "wrong_password"
    weak = client.post(url, headers=_bearer(token), json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422 and _code(weak) == "weak_password"
    assert client.post(url, json={"current_password": PASSWORD, "new_password": "fresh-password"}).status_code == 401

    response = client.post(url, headers=_bearer(token), json={"current_password": PASSWORD, "new_password": "fresh-password"})
    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    assert client.get("/api/profile/me", headers=_bearer(token)).status_code == 401
    assert client.get("/api/profile/me", headers=_bearer(new_token)).status_code == 200
    assert _login(client, EMAIL, "fresh-password").status_code == 200


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
def test_token_claims_use_user_id_and_version(client, college, make_user):
    from jose import jwt

    user, headers = make_user("claims@djsce.ac.in", "Claims", college)
    payload = jwt.decode(headers["Authorization"].split()[1], settings.JWT_SECRET_KEY,
                         algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(user.id)
    assert payload["tv"] == 0


@pytest.mark.parametrize("claims", [
    lambda user: {"sub": str(user.id), "tv": 1},          # stale/forged version
    lambda user: {"sub": str(user.id)},                   # no version
    lambda user: {"sub": str(user.id), "tv": "0"},        # wrong type
    lambda user: {"sub": user.email, "tv": 0},            # pre-migration style token
    lambda user: {"sub": "99999", "tv": 0},               # unknown user
])
def test_invalid_token_claims_are_rejected(client, college, make_user, claims):
    user, _ = make_user("tv@djsce.ac.in", "Token Version", college)
    token = auth_service.create_access_token(claims(user))
    assert client.get("/api/profile/me", headers=_bearer(token)).status_code == 401


def test_revoked_token_cannot_open_websockets(client, college, make_user, test_session_factory):
    user, headers = make_user("socket@djsce.ac.in", "Socket", college)
    token = headers["Authorization"].split()[1]
    with test_session_factory() as db:
        db.get(user_model.User, user.id).token_version = 1
        db.commit()
    for path in ("/api/ws/chat", "/api/ws/pool"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, subprotocols=["token", token]) as ws:
                ws.receive_json()


# --------------------------------------------------------------------------
# Email backends
# --------------------------------------------------------------------------
def test_console_backend_logs_code_with_masked_email(caplog):
    caplog.set_level(logging.WARNING, logger="app.services.email_service")
    email_service.ConsoleEmailSender().send(
        email_service.code_email("student@djsce.ac.in", "123456", "VERIFY", 10))
    [record] = [r for r in caplog.records if "Verification code" in r.getMessage()]
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert message.startswith("Verification code for s***@djsce.ac.in: 123456")
    assert "student@" not in message
    # The handlers' redaction filter keeps the code readable.
    assert RedactSecretsFilter().filter(record) is True
    assert "123456" in record.getMessage()


def test_smtp_backend_sends_with_starttls_and_never_logs_code(monkeypatch, caplog):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, message):
            calls.append(("send", message["To"], message.get_content()))

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    caplog.set_level(logging.DEBUG)
    sender = email_service.SmtpEmailSender("smtp.example.invalid", 587, "mailer", "pw", "noreply@example.invalid")
    sender.send(email_service.code_email("student@djsce.ac.in", "654321", "RESET", 10))
    assert ("starttls",) in calls and ("login", "mailer") in calls
    assert calls.index(("starttls",)) < calls.index(("login", "mailer"))
    assert any(c[0] == "send" and "654321" in c[2] for c in calls)
    assert "654321" not in caplog.text


def test_smtp_backend_selected_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@example.invalid")
    assert isinstance(email_service.build_sender_from_settings(), email_service.SmtpEmailSender)
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "console")
    assert isinstance(email_service.build_sender_from_settings(), email_service.ConsoleEmailSender)


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------
def test_profile_includes_verification_and_birth_date(client, college, make_user, test_session_factory):
    user, headers = make_user("profile@djsce.ac.in", "Profile", college)
    body = client.get("/api/profile/me", headers=headers).json()
    assert body["email_verified"] is True
    assert body["date_of_birth"] == "2000-01-01"
    with test_session_factory() as db:
        row = db.get(user_model.User, user.id)
        row.date_of_birth = None
        row.email_verified_at = None
        db.commit()
    body = client.get("/api/profile/me", headers=headers).json()
    assert body["email_verified"] is False
    assert body["date_of_birth"] is None
