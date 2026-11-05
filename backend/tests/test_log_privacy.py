"""Location data must not reach INFO-or-higher log records.

Coordinates are user location data. Route requests and invalid-coordinate
rejections are logged with generic messages only; exact numbers may appear at
DEBUG at most, and these tests run at INFO.
"""

import logging

import httpx

LAT_SENTINEL = "12.3456"
LNG_SENTINEL = "65.4321"

ROUTE_BODY = {
    "start_lat": 12.3456,
    "start_lng": 65.4321,
    "end_lat": 12.9999,
    "end_lng": 65.1111,
}


def _fake_500(monkeypatch):
    async def _send(self, request, *args, **kwargs):
        return httpx.Response(500, text="internal", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)


def _info_and_above(caplog):
    return "\n".join(
        record.getMessage() for record in caplog.records if record.levelno >= logging.INFO
    )


def test_route_request_logs_no_coordinates_at_info(client, college, make_user, monkeypatch, caplog):
    _, headers = make_user("privlog@example.test", "Priv Log", college, phone="+10000000201")
    _fake_500(monkeypatch)
    caplog.set_level(logging.INFO)

    response = client.post("/api/map/route", json=ROUTE_BODY, headers=headers)

    assert response.status_code == 502
    logged = _info_and_above(caplog)
    assert "Route requested" in logged
    assert LAT_SENTINEL not in logged
    assert LNG_SENTINEL not in logged


def test_invalid_coordinates_log_no_coordinates(client, college, make_user, caplog):
    _, headers = make_user("privbad@example.test", "Priv Bad", college, phone="+10000000202")
    caplog.set_level(logging.INFO)
    body = dict(ROUTE_BODY, start_lat=123.0, start_lng=65.4321)

    response = client.post("/api/map/route", json=body, headers=headers)

    assert response.status_code == 400
    logged = _info_and_above(caplog)
    assert "Invalid coordinates rejected" in logged
    assert "123.0" not in logged
    assert LNG_SENTINEL not in logged
