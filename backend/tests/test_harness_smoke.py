"""Smoke tests proving the offline harness works end to end."""

import asyncio
import logging

import httpx
import pytest


def test_health_ping_returns_200(client):
    response = client.get("/api/health/ping")

    assert response.status_code == 200
    assert response.json() == {"ping": "pong!"}


def test_protected_endpoint_rejects_missing_token(client):
    response = client.get("/api/pool/connections/active")

    assert response.status_code in (401, 403)


def test_authenticated_call_succeeds(client, college, make_user):
    _, headers = make_user("alice@example.test", "Alice Example", college, phone="+10000000001")

    response = client.get("/api/pool/connections/active", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"connection": None}


def test_block_network_blocks_provider_call(client, college, make_user, caplog):
    # Direct check: the patched AsyncClient fails immediately, no socket is opened.
    async def _try_request():
        async with httpx.AsyncClient() as http:
            await http.get("https://api.olamaps.io/routing/v1/directions")

    with pytest.raises(RuntimeError, match="network disabled in tests"):
        asyncio.run(_try_request())

    # Through the app: map_service catches every exception and returns None,
    # so the route answers with an error status rather than a route.
    _, headers = make_user("bob@example.test", "Bob Example", college, phone="+10000000002")
    body = {"start_lat": 19.07, "start_lng": 72.87, "end_lat": 19.13, "end_lng": 72.83}

    with caplog.at_level(logging.ERROR):
        response = client.post("/api/map/route", json=body, headers=headers)

    assert response.status_code >= 400
    assert "network disabled in tests" in caplog.text
