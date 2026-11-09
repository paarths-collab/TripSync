"""Places proxy (/api/map/places/*) and the /api/map/route cache.

Provider traffic is faked by replacing httpx.AsyncClient.send. The Ola key
must reach the provider request but never a response or a log line, and
search text / coordinates must not be logged above DEBUG.
"""

import logging

import httpx
import pytest

from app.core.config import settings
from app.services import map_service

SENTINEL = "test-ola-key-SENTINEL"
VALID_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

AUTOCOMPLETE_BODY = {
    "status": "ok",
    "predictions": [
        {
            "place_id": "ola-1",
            "description": "Andheri Station, Andheri West, Mumbai, Maharashtra",
            "structured_formatting": {"main_text": "Andheri Station", "secondary_text": "Andheri West, Mumbai"},
            "geometry": {"location": {"lat": 19.1197, "lng": 72.8468}},
        },
        {"place_id": "ola-2", "description": "Andheri East, Mumbai"},   # no structured_formatting
        {"description": "missing place id"},                             # dropped
        "garbage",                                                       # dropped
    ],
}
DETAILS_BODY = {
    "status": "ok",
    "result": {
        "place_id": "ola-1",
        "name": "Andheri Station",
        "formatted_address": "Andheri Station, Andheri West, Mumbai, Maharashtra 400058",
        "geometry": {"location": {"lat": 19.1197, "lng": 72.8468}},
    },
}
REVERSE_BODY = {
    "status": "ok",
    "results": [
        {"formatted_address": "Vile Parle West, Mumbai, Maharashtra", "name": "Vile Parle West",
         "geometry": {"location": {"lat": 19.1, "lng": 72.84}}},
    ],
}


class FakeProvider:
    """Replaces AsyncClient.send; records requests; answers from a responder."""

    def __init__(self, monkeypatch, responder):
        self.requests = []
        self.responder = responder
        provider = self

        async def _send(client, request, *args, **kwargs):
            provider.requests.append(request)
            return provider.responder(request)

        monkeypatch.setattr(httpx.AsyncClient, "send", _send)


def _json(body, status=200):
    return lambda request: httpx.Response(status, json=body, request=request)


@pytest.fixture
def headers(college, make_user):
    return make_user("places@djsce.ac.in", "Places User", college)[1]


def _get(client, path, headers, **params):
    return client.get(f"/api/map/places/{path}", params=params, headers=headers)


def _assert_code(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert SENTINEL not in response.text


# --------------------------------------------------------------------------
# Autocomplete
# --------------------------------------------------------------------------
def test_autocomplete_normalises_predictions(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json(AUTOCOMPLETE_BODY))
    response = _get(client, "autocomplete", headers, input="  andheri  stn ", lat=19.11, lng=72.85)
    assert response.status_code == 200
    assert response.json() == {"predictions": [
        {"place_id": "ola-1", "description": "Andheri Station, Andheri West, Mumbai, Maharashtra",
         "main_text": "Andheri Station", "secondary_text": "Andheri West, Mumbai"},
        {"place_id": "ola-2", "description": "Andheri East, Mumbai",
         "main_text": "Andheri East", "secondary_text": "Mumbai"},
    ]}
    assert SENTINEL not in response.text
    [request] = fake.requests
    assert request.url.path == "/places/v1/autocomplete"
    assert request.url.params["input"] == "andheri stn"
    assert request.url.params["location"] == "19.11,72.85"
    assert request.url.params["api_key"] == SENTINEL


def test_autocomplete_without_bias(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json({"status": "ok", "predictions": []}))
    response = _get(client, "autocomplete", headers, input="bandra")
    assert response.status_code == 200 and response.json() == {"predictions": []}
    assert "location" not in fake.requests[0].url.params


@pytest.mark.parametrize("params", [
    {"input": "ab"},
    {"input": "   abc"[:5]},
    {"input": "bandra", "lat": 19.1},
    {"input": "bandra", "lng": 72.8},
    {"input": "bandra", "lat": 91, "lng": 72.8},
    {"input": "bandra", "lat": 19.1, "lng": 181},
    {"input": "bandra", "lat": "north", "lng": 72.8},
    {},
    {"input": "x" * 201},
])
def test_autocomplete_bad_input(client, headers, params):
    _assert_code(client.get("/api/map/places/autocomplete", params=params, headers=headers), 422, "invalid_request")


def test_places_require_authentication(client):
    assert client.get("/api/map/places/autocomplete", params={"input": "bandra"}).status_code == 401
    assert client.get("/api/map/places/details", params={"place_id": "x"}).status_code == 401
    assert client.get("/api/map/places/reverse-geocode", params={"lat": 1, "lng": 2}).status_code == 401


# --------------------------------------------------------------------------
# Provider failures
# --------------------------------------------------------------------------
def _timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


def _connect_error(request):
    raise httpx.ConnectError(f"cannot reach {request.url}", request=request)


@pytest.mark.parametrize("path, params", [
    ("autocomplete", {"input": "bandra"}),
    ("details", {"place_id": "ola-1"}),
    ("reverse-geocode", {"lat": 19.1, "lng": 72.84}),
])
@pytest.mark.parametrize("responder, status, code", [
    (_timeout, 504, "maps_timeout"),
    (_connect_error, 502, "maps_unavailable"),
    (_json({"error": "boom"}, status=500), 502, "maps_unavailable"),
    (_json({"error": "forbidden"}, status=403), 502, "maps_unavailable"),
    (lambda request: httpx.Response(200, content=b"<html>blocked</html>", request=request), 502, "maps_unavailable"),
    (_json({"status": "REQUEST_DENIED", "error_message": f"bad key {SENTINEL}"}), 502, "maps_unavailable"),
    (_json(["not", "an", "object"]), 502, "maps_unavailable"),
])
def test_provider_failures(client, headers, monkeypatch, caplog, path, params, responder, status, code):
    caplog.set_level(logging.DEBUG)
    FakeProvider(monkeypatch, responder)
    _assert_code(_get(client, path, headers, **params), status, code)
    assert SENTINEL not in caplog.text


# --------------------------------------------------------------------------
# Details
# --------------------------------------------------------------------------
def test_details_normalised(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json(DETAILS_BODY))
    response = _get(client, "details", headers, place_id="ola-1")
    assert response.status_code == 200
    assert response.json() == {
        "place_id": "ola-1", "name": "Andheri Station",
        "address": "Andheri Station, Andheri West, Mumbai, Maharashtra 400058",
        "lat": 19.1197, "lng": 72.8468,
    }
    assert fake.requests[0].url.path == "/places/v1/details"
    assert fake.requests[0].url.params["place_id"] == "ola-1"


def test_details_name_falls_back_to_address(client, headers, monkeypatch):
    body = {"status": "ok", "result": {"formatted_address": "Gate 2, Powai, Mumbai",
                                       "geometry": {"location": {"lat": "19.12", "lng": "72.9"}}}}
    FakeProvider(monkeypatch, _json(body))
    response = _get(client, "details", headers, place_id="ola-9")
    assert response.json() == {"place_id": "ola-9", "name": "Gate 2", "address": "Gate 2, Powai, Mumbai",
                               "lat": 19.12, "lng": 72.9}


@pytest.mark.parametrize("responder", [
    _json({"error": "not found"}, status=404),
    _json({"error": "invalid place"}, status=400),
    _json({"status": "zero_results"}),
    _json({"status": "ok", "result": None}),
])
def test_details_unknown_place(client, headers, monkeypatch, responder):
    FakeProvider(monkeypatch, responder)
    _assert_code(_get(client, "details", headers, place_id="nope"), 422, "invalid_request")


def test_details_without_coordinates_is_provider_error(client, headers, monkeypatch):
    FakeProvider(monkeypatch, _json({"status": "ok", "result": {"name": "X", "geometry": {"location": {"lat": 500}}}}))
    _assert_code(_get(client, "details", headers, place_id="ola-1"), 502, "maps_unavailable")


def test_details_requires_place_id(client, headers):
    _assert_code(client.get("/api/map/places/details", headers=headers), 422, "invalid_request")
    _assert_code(_get(client, "details", headers, place_id="   "), 422, "invalid_request")


# --------------------------------------------------------------------------
# Reverse geocode
# --------------------------------------------------------------------------
def test_reverse_geocode_normalised(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json(REVERSE_BODY))
    response = _get(client, "reverse-geocode", headers, lat=19.1, lng=72.84)
    assert response.status_code == 200
    assert response.json() == {"address": "Vile Parle West, Mumbai, Maharashtra", "name": "Vile Parle West"}
    assert fake.requests[0].url.path == "/places/v1/reverse-geocode"
    assert fake.requests[0].url.params["latlng"] == "19.1,72.84"


def test_reverse_geocode_without_results_uses_coordinates(client, headers, monkeypatch):
    FakeProvider(monkeypatch, _json({"status": "zero_results", "results": []}))
    response = _get(client, "reverse-geocode", headers, lat=19.123456, lng=72.8)
    assert response.json() == {"address": "19.12346, 72.80000", "name": "19.12346, 72.80000"}


@pytest.mark.parametrize("params", [{"lat": 19.1}, {"lng": 72.8}, {"lat": -91, "lng": 0}, {"lat": 0, "lng": 200}])
def test_reverse_geocode_bad_input(client, headers, params):
    _assert_code(client.get("/api/map/places/reverse-geocode", params=params, headers=headers), 422, "invalid_request")


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
def test_places_results_are_cached(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json(AUTOCOMPLETE_BODY))
    for text in ("Andheri", "andheri", " ANDHERI "):
        assert _get(client, "autocomplete", headers, input=text).status_code == 200
    assert len(fake.requests) == 1
    assert _get(client, "autocomplete", headers, input="andheri", lat=19.1, lng=72.8).status_code == 200
    assert len(fake.requests) == 2  # a different bias is a different query

    fake.responder = _json(DETAILS_BODY)
    _get(client, "details", headers, place_id="ola-1")
    _get(client, "details", headers, place_id="ola-1")
    assert len(fake.requests) == 3

    fake.responder = _json(REVERSE_BODY)
    _get(client, "reverse-geocode", headers, lat=19.1, lng=72.84)
    _get(client, "reverse-geocode", headers, lat=19.100001, lng=72.840001)  # same point to ~1 m
    assert len(fake.requests) == 4


def test_cache_entries_expire(client, headers, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(map_service.places_cache, "_clock", lambda: now[0])
    fake = FakeProvider(monkeypatch, _json(AUTOCOMPLETE_BODY))
    _get(client, "autocomplete", headers, input="andheri")
    now[0] += settings.PLACES_CACHE_TTL_SECONDS + 1
    _get(client, "autocomplete", headers, input="andheri")
    assert len(fake.requests) == 2


def test_failures_are_not_cached(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json({"error": "boom"}, status=500))
    assert _get(client, "autocomplete", headers, input="andheri").status_code == 502
    fake.responder = _json(AUTOCOMPLETE_BODY)
    assert _get(client, "autocomplete", headers, input="andheri").status_code == 200
    assert len(fake.requests) == 2


def test_cache_is_bounded():
    from app.core.ttl_cache import MISSING, TTLCache

    cache = TTLCache(max_entries=2)
    for key in "abc":
        cache.set(key, key, 60)
    assert len(cache) == 2 and cache.get("a") is MISSING and cache.get("c") == "c"


def test_route_is_cached(client, headers, monkeypatch):
    body = {"status": "SUCCESS", "routes": [{"overview_polyline": VALID_POLYLINE,
                                             "legs": [{"distance": 1000, "duration": 120}]}]}
    fake = FakeProvider(monkeypatch, _json(body))
    route = {"start_lat": 19.07, "start_lng": 72.87, "end_lat": 19.13, "end_lng": 72.83}
    first = client.post("/api/map/route", json=route, headers=headers)
    second = client.post("/api/map/route", json=route, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(fake.requests) == 1
    client.post("/api/map/route", json=dict(route, end_lat=19.2), headers=headers)
    assert len(fake.requests) == 2


def test_route_failures_are_not_cached(client, headers, monkeypatch):
    fake = FakeProvider(monkeypatch, _json({"error": "boom"}, status=500))
    route = {"start_lat": 19.07, "start_lng": 72.87, "end_lat": 19.13, "end_lng": 72.83}
    assert client.post("/api/map/route", json=route, headers=headers).status_code == 502
    assert client.post("/api/map/route", json=route, headers=headers).status_code == 502
    assert len(fake.requests) == 2


# --------------------------------------------------------------------------
# Proxy setting and privacy
# --------------------------------------------------------------------------
def test_ola_proxy_setting_is_used_for_every_call(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "OLA_MAPS_PROXY", "http://proxy.example.invalid:8080")
    assert map_service.ola_client_kwargs(5.0) == {"timeout": 5.0, "proxy": "http://proxy.example.invalid:8080"}
    monkeypatch.setattr(settings, "OLA_MAPS_PROXY", None)
    assert map_service.ola_client_kwargs(5.0) == {"timeout": 5.0}

    seen = []
    real_init = httpx.AsyncClient.__init__

    def recording_init(self, *args, **kwargs):
        seen.append(kwargs.get("proxy"))
        kwargs.pop("proxy", None)  # never actually dial the fake proxy
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(settings, "OLA_MAPS_PROXY", "http://proxy.example.invalid:8080")
    monkeypatch.setattr(httpx.AsyncClient, "__init__", recording_init)
    FakeProvider(monkeypatch, _json(AUTOCOMPLETE_BODY))
    _get(client, "autocomplete", headers, input="andheri")
    FakeProvider(monkeypatch, _json({"status": "SUCCESS", "routes": []}))
    client.post("/api/map/route", json={"start_lat": 19, "start_lng": 72, "end_lat": 20, "end_lng": 73},
                headers=headers)
    assert seen == ["http://proxy.example.invalid:8080"] * 2


def test_query_text_and_coordinates_not_logged_above_debug(client, headers, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    FakeProvider(monkeypatch, _json({"error": "boom"}, status=500))
    _get(client, "autocomplete", headers, input="secret street name", lat=12.3456, lng=65.4321)
    _get(client, "reverse-geocode", headers, lat=12.3456, lng=65.4321)
    _get(client, "details", headers, place_id="private-place-id")
    logged = "\n".join(r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG)
    for secret in ("secret street name", "12.3456", "65.4321", "12.35", "private-place-id", SENTINEL):
        assert secret not in logged
