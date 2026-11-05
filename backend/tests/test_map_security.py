"""Security and error-handling tests for the map routing endpoint.

All provider traffic is faked by overriding httpx.AsyncClient.send per test.
The API key sentinel must never reach a response body or a log record.
"""

import asyncio
import logging

import httpx
import pytest

from app import main as app_main
from app.core.log_redaction import RedactSecretsFilter
from app.services import map_service

SENTINEL = "test-ola-key-SENTINEL"

ROUTE_BODY = {"start_lat": 19.07, "start_lng": 72.87, "end_lat": 19.13, "end_lng": 72.83}

# Standard encoded polyline (three points); decodes to valid geometry.
VALID_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def _fake_send(monkeypatch, responder):
    """Route every AsyncClient.send through responder(request) -> Response or raises."""

    async def _send(self, request, *args, **kwargs):
        return responder(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)


def _respond_with(response_factory):
    def _responder(request):
        return response_factory(request)

    return _responder


def _post_route(client, headers):
    return client.post("/api/map/route", json=ROUTE_BODY, headers=headers)


# --------------------------------------------------------------------------
# Debug endpoint is gone
# --------------------------------------------------------------------------
def test_ola_debug_endpoint_is_removed(client, college, make_user):
    _, headers = make_user("debug@example.test", "Debug User", college, phone="+10000000003")

    response = client.get(
        "/api/map/debug/ola-test?start_lat=1&start_lng=1&end_lat=2&end_lng=2",
        headers=headers,
    )

    assert response.status_code in (404, 405)
    assert SENTINEL not in response.text


# --------------------------------------------------------------------------
# POST /api/map/route status mapping
# --------------------------------------------------------------------------
def test_route_read_timeout_returns_504(client, college, make_user, monkeypatch):
    _, headers = make_user("t1@example.test", "Timeout One", college, phone="+10000000004")

    def _raise_timeout(request):
        raise httpx.ReadTimeout("t", request=request)

    _fake_send(monkeypatch, _raise_timeout)

    response = _post_route(client, headers)

    assert response.status_code == 504
    assert response.json()["detail"] == "Routing provider timed out"
    assert SENTINEL not in response.text


def test_route_provider_500_returns_502(client, college, make_user, monkeypatch):
    _, headers = make_user("s500@example.test", "Server Error", college, phone="+10000000005")

    _fake_send(
        monkeypatch,
        _respond_with(lambda req: httpx.Response(500, text="internal", request=req)),
    )

    response = _post_route(client, headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "Routing provider unavailable"
    assert SENTINEL not in response.text


def test_route_invalid_json_returns_502(client, college, make_user, monkeypatch):
    _, headers = make_user("json@example.test", "Bad Json", college, phone="+10000000006")

    _fake_send(
        monkeypatch,
        _respond_with(
            lambda req: httpx.Response(200, content=b"<html>not json</html>", request=req)
        ),
    )

    response = _post_route(client, headers)

    assert response.status_code == 502
    assert SENTINEL not in response.text


def test_route_non_success_status_returns_502(client, college, make_user, monkeypatch):
    _, headers = make_user("fail@example.test", "Provider Fail", college, phone="+10000000007")

    provider_body = {"status": "INVALID_KEY", "error_message": f"bad key {SENTINEL}"}
    _fake_send(
        monkeypatch,
        _respond_with(lambda req: httpx.Response(200, json=provider_body, request=req)),
    )

    response = _post_route(client, headers)

    assert response.status_code == 502
    assert SENTINEL not in response.text


def test_route_success_with_empty_routes_returns_404(client, college, make_user, monkeypatch):
    _, headers = make_user("empty@example.test", "No Route", college, phone="+10000000008")

    _fake_send(
        monkeypatch,
        _respond_with(
            lambda req: httpx.Response(200, json={"status": "SUCCESS", "routes": []}, request=req)
        ),
    )

    response = _post_route(client, headers)

    assert response.status_code == 404
    assert SENTINEL not in response.text


def test_route_success_returns_route(client, college, make_user, monkeypatch):
    _, headers = make_user("ok@example.test", "Good Route", college, phone="+10000000009")

    payload = {
        "status": "SUCCESS",
        "routes": [
            {
                "overview_polyline": VALID_POLYLINE,
                "legs": [{"distance": 1234.5, "duration": 300.2}],
            }
        ],
    }
    _fake_send(
        monkeypatch,
        _respond_with(lambda req: httpx.Response(200, json=payload, request=req)),
    )

    response = _post_route(client, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["route"]["distance_meters"] == 1234
    assert body["route"]["duration_seconds"] == 300
    assert len(body["route"]["polyline"]) == 3
    assert SENTINEL not in response.text


def test_service_success_is_not_fallback(monkeypatch):
    payload = {
        "status": "SUCCESS",
        "routes": [
            {
                "overview_polyline": VALID_POLYLINE,
                "legs": [{"distance": 10, "duration": 20}],
            }
        ],
    }
    _fake_send(
        monkeypatch,
        _respond_with(lambda req: httpx.Response(200, json=payload, request=req)),
    )

    result = asyncio.run(map_service.get_route_from_ola(19.07, 72.87, 19.13, 72.83))

    assert result is not None
    assert result["is_fallback"] is False


def test_service_timeout_raises_timeout_error(monkeypatch):
    def _raise_timeout(request):
        raise httpx.ReadTimeout("t", request=request)

    _fake_send(monkeypatch, _raise_timeout)

    with pytest.raises(map_service.RoutingProviderTimeout):
        asyncio.run(map_service.get_route_from_ola(19.07, 72.87, 19.13, 72.83))


def test_service_timeout_is_a_provider_error():
    assert issubclass(map_service.RoutingProviderTimeout, map_service.RoutingProviderError)


# --------------------------------------------------------------------------
# Logging must never contain the key
# --------------------------------------------------------------------------
def test_timeout_and_500_logs_do_not_contain_key(client, college, make_user, monkeypatch, caplog):
    _, headers = make_user("logs@example.test", "Log Check", college, phone="+10000000010")

    caplog.set_level(logging.DEBUG)

    def _raise_timeout(request):
        raise httpx.ReadTimeout("t", request=request)

    _fake_send(monkeypatch, _raise_timeout)
    timeout_response = _post_route(client, headers)

    _fake_send(
        monkeypatch,
        _respond_with(lambda req: httpx.Response(500, text="boom", request=req)),
    )
    error_response = _post_route(client, headers)

    assert timeout_response.status_code == 504
    assert error_response.status_code == 502
    assert SENTINEL not in caplog.text


# --------------------------------------------------------------------------
# Redaction filter
# --------------------------------------------------------------------------
def _record(msg, args=()):
    return logging.LogRecord("test.logger", logging.INFO, __file__, 1, msg, args, None)


def _filtered_message(record):
    assert RedactSecretsFilter().filter(record) is True
    return record.getMessage()


def test_filter_redacts_query_string_key():
    record = _record(
        f"HTTP Request: POST https://api.example.test/route?api_key={SENTINEL}&x=1"
    )

    message = _filtered_message(record)

    assert "[REDACTED]" in message
    assert SENTINEL not in message
    assert "x=1" in message


def test_filter_redacts_key_passed_as_arg():
    record = _record(
        "HTTP Request: %s %s",
        ("POST", f"https://api.example.test/route?api_key={SENTINEL}&x=1"),
    )

    message = _filtered_message(record)

    assert "[REDACTED]" in message
    assert SENTINEL not in message


def test_filter_redacts_dict_repr_with_args():
    record = _record("params=%r", ({"api_key": SENTINEL},))

    message = _filtered_message(record)

    assert "[REDACTED]" in message
    assert SENTINEL not in message


def test_filter_redacts_dict_repr_literal():
    record = _record(f"{{'api_key': '{SENTINEL}'}}")

    message = _filtered_message(record)

    assert "[REDACTED]" in message
    assert SENTINEL not in message


def test_filter_redacts_literal_configured_secret():
    record = _record(f"raw value was {SENTINEL} somewhere")

    message = _filtered_message(record)

    assert "[REDACTED]" in message
    assert SENTINEL not in message


def test_redaction_filter_is_attached_to_configured_handlers():
    import logging as _logging

    configured = [
        app_main.file_handler,
        app_main.error_handler,
        app_main.console_handler,
    ]
    for handler in configured:
        assert any(isinstance(f, RedactSecretsFilter) for f in handler.filters), handler

    root = _logging.getLogger()
    assert app_main.console_handler in root.handlers


def test_httpx_loggers_are_quiet():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
