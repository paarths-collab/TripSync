# backend/app/routes/chat_ws_router.py

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import auth_service, campus_outbox, connection_access
from app.core.ws_manager import manager
from app.models import user_model

logger = logging.getLogger(__name__)

router = APIRouter()

NOT_AUTHORIZED_DETAIL = "Chat is only available with an approved ride partner"


async def _send_error(websocket: WebSocket, code: str, detail: str) -> bool:
    """Send an error frame to this client only. Returns False if the socket is dead."""
    try:
        await websocket.send_json({"type": "error", "code": code, "detail": detail})
        return True
    except Exception:
        return False


@router.websocket("/ws/chat")
async def chat_websocket(
    websocket: WebSocket,
    # Authenticated exactly like /ws/pool: subprotocols ['token', <jwt>].
    current_user: user_model.User = Depends(auth_service.get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Dedicated WebSocket endpoint for chat messaging.
    Separate from pooling WebSocket to avoid conflicts.

    Connect with subprotocols ['token', <jwt>]. Chat messages are relayed only
    between users who share an active ride connection, re-checked against the
    database for every message.
    """
    if not current_user:
        await websocket.close(code=1008)
        return

    user_id = current_user.id

    # Echo only the protocol name 'token' (never the JWT) when the client offered it.
    offered = websocket.scope.get("subprotocols", [])
    await manager.connect(
        user_id, websocket, subprotocol="token" if "token" in offered else None
    )

    try:
        await campus_outbox.flush_on_connect(db, user_id)
        while True:
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                if not await _send_error(websocket, "invalid_message", "Frame is not valid JSON"):
                    break
                continue

            if not isinstance(message_data, dict):
                if not await _send_error(websocket, "invalid_message", "Frame must be a JSON object"):
                    break
                continue

            msg_type = message_data.get("type")

            if msg_type == "ping":
                # Respond to ping to keep connection alive
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
                continue

            if msg_type != "chat_message":
                continue

            content = message_data.get("content")
            receiver_id = message_data.get("receiver_id")
            if not isinstance(content, str) or not content or receiver_id is None:
                if not await _send_error(
                    websocket, "invalid_message", "chat_message requires receiver_id and content"
                ):
                    break
                continue

            # Fresh state per message: end the open transaction and expire the
            # session so a ride cancelled mid-socket is honoured.
            db.rollback()
            db.expire_all()
            grant = connection_access.authorize_relay(
                db, user_id, receiver_id,
                message_data.get("connection_id"), message_data.get("party_id"),
            )
            if grant is None:
                if not await _send_error(websocket, "not_authorized", NOT_AUTHORIZED_DETAIL):
                    break
                continue

            await manager.send_personal_message(
                {
                    "type": "chat_message",
                    "message_id": message_data.get("message_id"),
                    **connection_access.grant_ref(grant),
                    "sender_id": user_id,
                    "content": content,
                    "created_at": message_data.get("created_at"),
                },
                receiver_id if isinstance(receiver_id, int) else int(receiver_id),
            )

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Chat WebSocket error for user %s", user_id)
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        manager.disconnect(user_id, websocket)
