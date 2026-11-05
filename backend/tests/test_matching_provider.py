"""Regression tests for the REAL distance-matrix helper (`_get_distances_from_ola`).

Only httpx.AsyncClient.send is replaced (overriding the autouse network block),
so URL/param building, response validation and error mapping are all exercised.
Provider failures must surface as explicit 502/504 errors, never as a 200 with
an empty match list, and must never leak the API key or provider response text.
"""

import logging

import httpx
import pytest

from app.models import pooling_model

SENTINEL = "test-ola-key-SENTINEL"
PROVIDER_TEXT_SENTINEL = "PROVIDER-RESPONSE-TEXT-SENTINEL"

START = {"start_latitude": 19.0760, "start_longitude": 72.8777}
DEST = {"destination_latitude": 19.1200, "destination_longitude": 72.9000, "destination_name": "Fictional Hall"}


def _body():
    return {**START, **DEST}


def _matrix(distance_for_each=1000, status="OK", count=None, top_status="SUCCESS"):
    def build(request):
        n = len(request.url.params["destinations"].split("|"))
        n = n if count is None else count
        return {
            "status": top_status,
            "rows": [{"elements": [{"status": status, "distance": distance_for_each} for _ in range(n)]}],
        }
    return build


@pytest.fixture
def seeded(client, college, make_user):
    """alice already has an ACTIVE request, so bob's search has one candidate."""
    alice, alice_h = make_user("alice@example.test", "Alice Example", college)
    bob, bob_h = make_user("bob@example.test", "Bob Example", college)
    # No candidates yet -> no provider call (network is blocked, so a call would raise).
    r = client.post("/api/pool/requests", json=_body(), headers=alice_h)
    assert r.status_code == 200 and r.json()["matches"] == []
    return {"alice": alice, "bob": bob, "alice_h": alice_h, "bob_h": bob_h}


def _install_send(monkeypatch, handler, calls=None):
    async def _send(self, request, *args, **kwargs):
        if calls is not None:
            calls.append(request)
        return handler(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)


def _assert_no_leak(response, caplog):
    assert SENTINEL not in response.text
    assert PROVIDER_TEXT_SENTINEL not in response.text
    assert SENTINEL not in caplog.text
    assert PROVIDER_TEXT_SENTINEL not in caplog.text


def _raise(exc):
    def handler(request):
        raise exc
    return handler


def _json_response(builder):
    def handler(request):
        return httpx.Response(200, json=builder(request), request=request)
    return handler


FAILURES = {
    "timeout": (_raise(httpx.ReadTimeout("slow " + SENTINEL)), 504),
    "connect_error": (_raise(httpx.ConnectError("refused " + SENTINEL)), 502),
    "http_500": (
        lambda request: httpx.Response(500, text="oops " + PROVIDER_TEXT_SENTINEL + SENTINEL, request=request),
        502,
    ),
    "invalid_json": (
        lambda request: httpx.Response(200, text="<html>Web Filter Violation " + PROVIDER_TEXT_SENTINEL + "</html>", request=request),
        502,
    ),
    "elements_shorter_than_destinations": (_json_response(_matrix(count=0)), 502),
    "rows_missing": (_json_response(lambda request: {"status": "SUCCESS", "rows": []}), 502),
    "non_success_status": (_json_response(_matrix(top_status="REQUEST_DENIED")), 502),
    "json_not_an_object": (_json_response(lambda request: ["SUCCESS"]), 502),
}


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_provider_failure_is_explicit_error_not_empty_matches(
    name, client, seeded, monkeypatch, caplog
):
    handler, expected_status = FAILURES[name]
    _install_send(monkeypatch, handler)

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == expected_status
    assert response.status_code != 200
    assert "matches" not in response.json()
    _assert_no_leak(response, caplog)


def test_valid_matrix_returns_the_match(client, seeded, monkeypatch, caplog):
    calls = []
    _install_send(monkeypatch, _json_response(_matrix(1000)), calls)

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert [m["id"] for m in matches] == [seeded["alice"].id]
    assert matches[0]["phone_number"] is None and matches[0]["email"] is None
    assert len(calls) == 2  # start check, then destination check
    _assert_no_leak(response, caplog)


def test_per_element_not_ok_is_a_legit_non_match(client, seeded, monkeypatch):
    _install_send(monkeypatch, _json_response(_matrix(status="ZERO_RESULTS")))

    response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_distance_above_radius_is_a_non_match(client, seeded, monkeypatch):
    _install_send(monkeypatch, _json_response(_matrix(5001)))

    response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_no_candidates_means_no_provider_call(client, college, make_user, monkeypatch):
    calls = []
    _install_send(monkeypatch, _json_response(_matrix(1000)), calls)
    _, headers = make_user("solo@example.test", "Solo Example", college)

    response = client.post("/api/pool/requests", json=_body(), headers=headers)

    assert response.status_code == 200
    assert response.json()["matches"] == []
    assert calls == []


def test_outbound_client_uses_tls_verification_and_no_proxies_kwarg(client, seeded, monkeypatch):
    seen = {}
    real_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        seen.update(kwargs)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)
    _install_send(monkeypatch, _json_response(_matrix(1000)))

    response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == 200
    assert seen.get("verify", True) is not False
    assert "proxies" not in seen


def test_provider_failure_cancels_the_ghost_request(client, seeded, monkeypatch, test_session_factory):
    """The search request is created before the provider fails. It must not stay
    ACTIVE as an un-searchable ghost other riders could match; it is cancelled
    (and committed) before the 502/504 goes out, and any pending invites rejected."""
    _install_send(monkeypatch, _raise(httpx.ReadTimeout("slow")))

    response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])
    assert response.status_code == 504

    db = test_session_factory()
    try:
        rows = db.query(pooling_model.PoolingRequest).filter_by(user_id=seeded["bob"].id).all()
        assert [r.status for r in rows] == [pooling_model.PoolingRequestStatus.CANCELLED]
        # alice's own request is untouched and still discoverable
        alice_rows = db.query(pooling_model.PoolingRequest).filter_by(user_id=seeded["alice"].id).all()
        assert [r.status for r in alice_rows] == [pooling_model.PoolingRequestStatus.ACTIVE]
    finally:
        db.close()


def test_ghost_request_is_not_visible_to_the_next_searcher(client, college, make_user, seeded, monkeypatch):
    _install_send(monkeypatch, _raise(httpx.ReadTimeout("slow")))
    assert client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"]).status_code == 504

    carol_calls = []
    _install_send(monkeypatch, _json_response(_matrix(1000)), carol_calls)
    _, carol_h = make_user("carol@example.test", "Carol Example", college)
    response = client.post("/api/pool/requests", json=_body(), headers=carol_h)

    assert response.status_code == 200
    # only alice (ACTIVE) is a candidate; bob's cancelled ghost is not
    assert [m["full_name"] for m in response.json()["matches"]] == ["Alice Example"]


def test_proxy_setting_is_passed_as_proxy_kwarg_never_proxies(client, seeded, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OLA_MAPS_PROXY", "http://127.0.0.1:9", raising=False)
    seen = {}
    real_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        seen.update(kwargs)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)
    _install_send(monkeypatch, _json_response(_matrix(1000)))

    response = client.post("/api/pool/requests", json=_body(), headers=seeded["bob_h"])

    assert response.status_code == 200
    assert seen.get("proxy") == "http://127.0.0.1:9"
    assert "proxies" not in seen
    assert seen.get("verify", True) is not False
