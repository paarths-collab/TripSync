"""In-process rate limiting: the limiter itself, client IP rules and the protected endpoints.

Rate limits are disabled for the rest of the suite (conftest); every test here
turns them on with small rules.
"""

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import Cooldown, RateLimiter, Rule, parse_rule


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def limits(monkeypatch):
    """limits(name="2/60", ...) enables rate limiting with the given rules."""

    def _set(**rules):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        for name, rule in rules.items():
            monkeypatch.setattr(settings, f"RATE_LIMIT_{name.upper()}", rule)

    return _set


def _assert_429(response):
    assert response.status_code == 429, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "too_many_requests"
    assert isinstance(detail["message"], str) and detail["message"]
    assert isinstance(detail["retry_after_seconds"], int) and detail["retry_after_seconds"] >= 1
    assert response.headers["Retry-After"] == str(detail["retry_after_seconds"])


# --------------------------------------------------------------------------
# Limiter units
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("10/60", Rule(10, 60.0)),
    (" 3/0.5 ", Rule(3, 0.5)),
    ("off", None), ("0", None), ("", None), (None, None), ("0/60", None),
])
def test_parse_rule(text, expected):
    assert parse_rule(text) == expected


def test_parse_rule_rejects_garbage():
    with pytest.raises(ValueError):
        parse_rule("ten per minute")


def test_sliding_window():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    rule = Rule(2, 60)
    assert limiter.hit("b", "k", rule) is None
    clock.now += 30
    assert limiter.hit("b", "k", rule) is None
    assert limiter.hit("b", "k", rule) == pytest.approx(30)   # first hit frees up at +60
    assert limiter.hit("b", "other", rule) is None              # keys are independent
    assert limiter.hit("other-bucket", "k", rule) is None       # buckets are independent
    clock.now += 30
    assert limiter.hit("b", "k", rule) is None
    assert limiter.hit("b", "k", rule) == pytest.approx(30)


def test_limiter_bounds_number_of_keys():
    limiter = RateLimiter(clock=FakeClock(), max_keys=3)
    for i in range(10):
        limiter.hit("b", str(i), Rule(1, 60))
    assert len(limiter._hits) == 3


def test_cooldown():
    clock = FakeClock()
    cooldown = Cooldown(clock=clock)
    assert cooldown.try_start("k", 60) == 0
    clock.now += 10
    assert cooldown.try_start("k", 60) == pytest.approx(50)
    assert cooldown.remaining("k") == pytest.approx(50)
    clock.now += 50
    assert cooldown.remaining("k") == 0
    assert cooldown.try_start("k", 60) == 0


def test_disabled_globally_and_per_rule(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_IP", "1/60")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    for _ in range(5):
        rate_limit.enforce("login_ip", "k")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_IP", "off")
    for _ in range(5):
        rate_limit.enforce("login_ip", "k")


# --------------------------------------------------------------------------
# Client IP
# --------------------------------------------------------------------------
def _ip_app():
    app = FastAPI()

    @app.get("/ip")
    def ip(request: Request):
        return {"ip": rate_limit.client_ip(request)}

    return app


def test_forwarded_for_ignored_without_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY", False)
    client = TestClient(_ip_app())
    body = client.get("/ip", headers={"X-Forwarded-For": "203.0.113.9"}).json()
    assert body["ip"] == "testclient"


def test_forwarded_for_used_behind_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    client = TestClient(_ip_app())
    # The left entry is client-controlled; the proxy appended the right one.
    headers = {"X-Forwarded-For": "198.51.100.1, 203.0.113.9"}
    assert client.get("/ip", headers=headers).json()["ip"] == "203.0.113.9"
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client.get("/ip", headers=headers).json()["ip"] == "198.51.100.1"
    assert client.get("/ip").json()["ip"] == "testclient"


def test_login_limit_keys_on_forwarded_client(client, limits, monkeypatch):
    limits(login_ip="1/60", login_email="off")
    monkeypatch.setattr(settings, "TRUSTED_PROXY", True)
    form = {"username": "a@djsce.ac.in", "password": "whatever-123"}
    assert client.post("/api/auth/token", data=form, headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 401
    _assert_429(client.post("/api/auth/token", data=form, headers={"X-Forwarded-For": "203.0.113.1"}))
    assert client.post("/api/auth/token", data=form, headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 401


# --------------------------------------------------------------------------
# Protected endpoints
# --------------------------------------------------------------------------
def test_login_limited_per_ip(client, limits):
    limits(login_ip="2/60", login_email="off")
    for i in range(2):
        assert client.post("/api/auth/token", data={"username": f"u{i}@djsce.ac.in", "password": "x" * 8}).status_code == 401
    _assert_429(client.post("/api/auth/token", data={"username": "u9@djsce.ac.in", "password": "x" * 8}))


def test_login_limited_per_email(client, limits):
    limits(login_ip="off", login_email="2/60")
    for _ in range(2):
        assert client.post("/api/auth/token", data={"username": "a@djsce.ac.in", "password": "x" * 8}).status_code == 401
    # Same address in another case counts against the same limit.
    _assert_429(client.post("/api/auth/token", data={"username": "A@DJSCE.ac.in", "password": "x" * 8}))
    assert client.post("/api/auth/token", data={"username": "b@djsce.ac.in", "password": "x" * 8}).status_code == 401


def test_register_limited_per_ip(client, college, limits):
    limits(register_ip="1/3600")
    body = {"email": "x@gmail.com", "full_name": "X", "password": "password-123",
            "college_id": college.id, "date_of_birth": "2000-01-01"}
    assert client.post("/api/auth/register", json=body).status_code == 422
    _assert_429(client.post("/api/auth/register", json=body))


def test_verify_request_limited_per_ip(client, limits):
    limits(verify_request_ip="2/3600")
    for i in range(2):
        assert client.post("/api/auth/verify-email/request", json={"email": f"u{i}@djsce.ac.in"}).status_code == 202
    _assert_429(client.post("/api/auth/verify-email/request", json={"email": "u9@djsce.ac.in"}))


def test_verify_confirm_limited_per_ip_and_email(client, limits):
    limits(verify_confirm_ip="off", verify_confirm_email="2/600")
    for _ in range(2):
        assert client.post("/api/auth/verify-email/confirm", json={"email": "a@djsce.ac.in", "code": "123456"}).status_code == 400
    _assert_429(client.post("/api/auth/verify-email/confirm", json={"email": "a@djsce.ac.in", "code": "123456"}))
    limits(verify_confirm_ip="1/600", verify_confirm_email="off")
    rate_limit.reset_all()
    assert client.post("/api/auth/verify-email/confirm", json={"email": "b@djsce.ac.in", "code": "123456"}).status_code == 400
    _assert_429(client.post("/api/auth/verify-email/confirm", json={"email": "c@djsce.ac.in", "code": "123456"}))


def test_password_forgot_and_reset_limited(client, limits):
    limits(password_forgot_ip="1/3600", password_reset_ip="off", password_reset_email="1/600")
    assert client.post("/api/auth/password/forgot", json={"email": "a@djsce.ac.in"}).status_code == 202
    _assert_429(client.post("/api/auth/password/forgot", json={"email": "b@djsce.ac.in"}))
    body = {"email": "a@djsce.ac.in", "code": "123456", "new_password": "new-password-1"}
    assert client.post("/api/auth/password/reset", json=body).status_code == 400
    _assert_429(client.post("/api/auth/password/reset", json=body))
    limits(password_reset_ip="1/600", password_reset_email="off")
    rate_limit.reset_all()
    assert client.post("/api/auth/password/reset", json=body).status_code == 400
    _assert_429(client.post("/api/auth/password/reset", json=dict(body, email="z@djsce.ac.in")))


def test_places_limited_per_user(client, college, make_user, limits, monkeypatch):
    limits(places_user="2/60")
    _, alice = make_user("alice@djsce.ac.in", "Alice", college)
    _, bob = make_user("bob@djsce.ac.in", "Bob", college)

    async def fake_send(self, request, *args, **kwargs):
        return httpx.Response(200, request=request, json={"status": "ok", "predictions": []})

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    assert client.get("/api/map/places/autocomplete?input=andheri", headers=alice).status_code == 200
    assert client.get("/api/map/places/reverse-geocode?lat=19.1&lng=72.8", headers=alice).status_code == 200
    _assert_429(client.get("/api/map/places/details?place_id=abc", headers=alice))
    assert client.get("/api/map/places/autocomplete?input=andheri", headers=bob).status_code == 200


def test_route_limited_per_user(client, college, make_user, limits):
    limits(route_user="1/60")
    _, headers = make_user("route@djsce.ac.in", "Route", college)
    body = {"start_lat": 19.0, "start_lng": 72.8, "end_lat": 19.1, "end_lng": 72.9}
    assert client.post("/api/map/route", json=body, headers=headers).status_code == 502  # provider blocked in tests
    _assert_429(client.post("/api/map/route", json=body, headers=headers))


def test_chat_messages_limited_per_user(client, college, make_user, limits):
    limits(chat_message_user="2/60")
    _, alice = make_user("alice@djsce.ac.in", "Alice", college)
    bob, _ = make_user("bob@djsce.ac.in", "Bob", college)
    body = {"receiver_id": bob.id, "content": "hello"}
    for _ in range(2):
        assert client.post("/api/chat/messages", json=body, headers=alice).status_code == 403  # no shared ride
    _assert_429(client.post("/api/chat/messages", json=body, headers=alice))


def test_unauthenticated_requests_are_rejected_before_counting(client, limits):
    limits(places_user="1/60")
    for _ in range(3):
        assert client.get("/api/map/places/autocomplete?input=andheri").status_code == 401
