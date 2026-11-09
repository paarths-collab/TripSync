"""Regression coverage for availability, privacy and failed-provider audit cases."""

import asyncio
from contextlib import ExitStack
from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app
from app.models import campus_model as cm, pooling_model as pm, service_model, user_model
from app.schemas import pooling_schema
from app.services import auth_service, campus_estimates, pooling_service, user_service
from scripts import seed_demo
from tests.campus_party_helpers import world  # noqa: F401


@pytest.mark.parametrize("path", ["/api/ws/chat", "/api/ws/pool"])
@pytest.mark.parametrize("authorized", [False, True])
def test_idle_sockets_release_database_connections(path, authorized, tmp_path):
    """Several open sockets and relays must leave a bounded pool free for REST."""
    engine = create_engine(f"sqlite:///{tmp_path}/sockets.db", pool_size=2,
                           max_overflow=0, pool_timeout=0.1,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, autoflush=False)
    with sf() as db:
        users = [user_model.User(email=f"socket{i}@example.test", full_name=f"Socket {i}",
                                 hashed_password="unused") for i in range(2)]
        db.add_all(users)
        db.flush()
        receiver = users[1].id
        if authorized:
            requests = [pm.PoolingRequest(user_id=u.id, status=pm.PoolingRequestStatus.CONNECTED,
                        start_latitude=19, start_longitude=72, destination_latitude=20,
                        destination_longitude=73) for u in users]
            db.add_all(requests)
            db.flush()
            db.add(pm.PoolingConnection(sender_request_id=requests[0].id,
                   receiver_request_id=requests[1].id, status=pm.PoolingConnectionStatus.APPROVED))
        db.commit()
    token = auth_service.create_access_token({"sub": "socket0@example.test"})
    def dependency():
        with sf() as db:
            yield db
    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = dependency
    client = TestClient(app)
    try:
        with ExitStack() as stack:
            for _ in range(3):  # deliberately more sockets than pool connections
                ws = stack.enter_context(client.websocket_connect(path, subprotocols=["token", token]))
                # Malformed-frame response also ensures connection setup finished.
                ws.send_text("not json")
                assert ws.receive_json()["code"] == "invalid_message"
                assert engine.pool.checkedout() == 0
                ws.send_json({"type": "chat_message", "receiver_id": receiver, "content": "Example"})
                if authorized:
                    # Barrier: the next frame is processed only after the relay finishes.
                    ws.send_text("not json")
                    assert ws.receive_json()["code"] == "invalid_message"
                else:
                    assert ws.receive_json()["code"] == "not_authorized"
                assert engine.pool.checkedout() == 0
            assert client.get("/api/campus/landmarks", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert engine.pool.checkedout() == 0
    finally:
        app.dependency_overrides[get_db] = previous
        client.close()
        engine.dispose()


@pytest.mark.parametrize("metrics", [{}, {"distance": 10}, {"duration": 20},
                                      {"distance": -1, "duration": 20},
                                      {"distance": True, "duration": 20},
                                      {"distance": 2_147_483_648, "duration": 20},
                                      {"distance": 10, "duration": "unknown"}])
def test_invalid_route_metrics_are_provider_failure(metrics, client, college, make_user,
                                                   monkeypatch, landmarks, test_session_factory, clock):
    _, headers = make_user("route@example.test", "Route Example", college)
    async def fake_send(self, request, *args, **kwargs):
        return httpx.Response(200, request=request, json={"status": "SUCCESS", "routes": [
            {"overview_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@", "legs": [metrics]}]})
    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    response = client.post("/api/map/route", headers=headers,
                           json={"start_lat": 19, "start_lng": 72, "end_lat": 20, "end_lng": 73})
    assert response.status_code == 502
    with test_session_factory() as db:
        estimate = asyncio.run(campus_estimates.corridor_estimate(
            db, landmarks["campus"], landmarks["hub"], "TO_HUB", clock.now))
        assert estimate.status == cm.EstimateStatus.UNVERIFIED
        assert estimate.duration_s is None


def test_old_suggestion_requires_current_deadline_ack(world, monkeypatch):
    async def route(*args):
        return {"distance_meters": 9000, "duration_seconds": 600}
    monkeypatch.setattr(campus_estimates.map_service, "get_route_from_ola", route)
    request = world.new_request("alice", start=0, end=60, arrive_by=world.clock.at(minutes=15))
    world.new_request("bob", start=0, end=60)
    suggestion = world.client.get(f"/api/campus/requests/{request.id}/suggestions",
                                  headers=world.headers["alice"]).json()["suggestions"][0]
    assert suggestion["warnings"] == []
    world.clock.advance(minutes=10)
    response = world.propose("alice", suggestion["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "warnings_unacknowledged"
    assert response.json()["detail"]["current"]["warnings"] == ["cannot_meet_arrive_by"]
    assert world.propose("alice", suggestion["id"], ack=True).status_code == 201


@pytest.mark.parametrize("password", ["x" * 73, "é" * 37])
def test_long_passwords_are_controlled_client_errors(password, client, college, make_user):
    response = client.post("/api/auth/register", json={"email": "long@example.com",
        "full_name": "Long Example", "college_name": "DJSCE", "password": password})
    assert response.status_code == 422
    make_user("login@example.test", "Login Example", college)
    assert client.post("/api/auth/token", data={"username": "login@example.test", "password": password}).status_code == 401


@pytest.mark.parametrize("password", ["x" * 72, "é" * 36])
def test_password_byte_limit_is_inclusive(password, client):
    response = client.post("/api/auth/register", json={"email": "limit@example.com",
        "full_name": "Limit Example", "college_name": "DJSCE", "password": password})
    assert response.status_code == 201
    assert client.post("/api/auth/token", data={"username": "limit@example.com", "password": password}).status_code == 200


def test_bad_password_hash_fails_authentication():
    assert user_service.verify_password("example", "invalid-hash") is False


def test_missing_service_post_is_404(client):
    assert client.get("/api/services/99999").status_code == 404


def test_anonymous_posts_hide_owner_except_from_owner(client, college, make_user, test_session_factory):
    user, owner_headers = make_user("anonymous@example.test", "Owner Example", college)
    _, other_headers = make_user("reader@example.test", "Reader Example", college)
    with test_session_factory() as db:
        post = service_model.ServicePost(poster_user_id=user.id, title="Example service",
            description="Example description", compensation_type=service_model.CompensationType.VOLUNTEER,
            is_anonymous=True)
        db.add(post)
        db.commit()
        post_id = post.id
    for headers in ({}, other_headers, owner_headers):
        detail = client.get(f"/api/services/{post_id}", headers=headers).json()
        listed = client.get("/api/services", headers=headers).json()[0]
        for view in (detail, listed):
            assert view["is_anonymous"] is True
            assert view["poster"] is None
            assert view["poster_user_id"] == (user.id if headers == owner_headers else None)
    with test_session_factory() as db:
        post = db.get(service_model.ServicePost, post_id)
        assert post.poster_user_id == user.id and post.poster.id == user.id
    # Owner permissions continue to use persisted ownership, not the public view.
    assert client.get(f"/api/services/{post_id}/applications", headers=owner_headers).status_code == 200
    assert client.delete(f"/api/services/{post_id}", headers=owner_headers).status_code == 204


def test_named_posts_keep_the_public_poster(client, college, make_user):
    user, headers = make_user("named@example.test", "Named Example", college)
    response = client.post("/api/services", headers=headers, json={
        "title": "Example service", "description": "Example description", "compensation_type": "volunteer",
    })
    assert response.status_code == 201
    post_id = response.json()["id"]
    for view in (client.get(f"/api/services/{post_id}").json(), client.get("/api/services").json()[0]):
        assert view["poster_user_id"] == user.id
        assert view["poster"]["full_name"] == "Named Example"


@pytest.mark.parametrize("demo_is_sender", [False, True])
def test_demo_reset_ends_surviving_legacy_partner_request(demo_is_sender, college, make_user, test_session_factory):
    demo, _ = make_user(seed_demo.DEMO_EMAILS[0], "Demo Example", college)
    rider, _ = make_user("regular@example.test", "Regular Example", college)
    with test_session_factory() as db:
        reqs = []
        for uid in (demo.id, rider.id):
            req = pm.PoolingRequest(user_id=uid, status=pm.PoolingRequestStatus.CONNECTED,
                  start_latitude=19, start_longitude=72, destination_latitude=20,
                  destination_longitude=73, destination_name="Example")
            db.add(req)
            db.flush()
            reqs.append(req.id)
        db.add(pm.PoolingConnection(sender_request_id=reqs[0 if demo_is_sender else 1],
               receiver_request_id=reqs[1 if demo_is_sender else 0], status=pm.PoolingConnectionStatus.APPROVED))
        db.commit()
        seed_demo.reset_demo(db)
        assert db.get(pm.PoolingRequest, reqs[1]).status == pm.PoolingRequestStatus.CANCELLED
        assert pooling_service.get_active_connection(db, rider.id) is None
        new_request = asyncio.run(pooling_service.create_or_update_pooling_request(
            db, db.get(user_model.User, rider.id), pooling_schema.PoolingRequestCreate(
                start_latitude=19, start_longitude=72, destination_latitude=20,
                destination_longitude=73, destination_name="Example")))
        assert new_request.status == pm.PoolingRequestStatus.ACTIVE
