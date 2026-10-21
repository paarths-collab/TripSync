# backend/app/core/ws_manager.py

import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # user_id -> every live socket for that user (several tabs/devices).
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket, subprotocol: Optional[str] = None):
        """Accepts a new WebSocket connection and stores it.

        subprotocol is echoed back in the handshake. Pass only a protocol name
        the client offered (e.g. "token"), never the credential itself: strict
        browser clients fail the handshake when they offered subprotocols and
        the server selects none.
        """
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.setdefault(user_id, []).append(websocket)
        logger.info("User %s connected via WebSocket.", user_id)

    def disconnect(self, user_id: int, websocket: Optional[WebSocket] = None):
        """Remove one socket for the user, or every socket if websocket is None."""
        sockets = self.active_connections.get(user_id)
        if sockets is None:
            return
        if websocket is None:
            sockets.clear()
        else:
            # Compare by identity: only the socket that is closing goes away.
            sockets[:] = [s for s in sockets if s is not websocket]
        if not sockets:
            self.active_connections.pop(user_id, None)
        logger.info("User %s disconnected from WebSocket.", user_id)

    async def send_personal_message(self, message: dict, user_id: int) -> int:
        """Send a JSON message to all of a user's sockets. Never raises.

        Returns the number of sockets that accepted the message (0 if the user
        has no live socket or every send failed).
        """
        delivered = 0
        for websocket in list(self.active_connections.get(user_id, [])):
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception as exc:  # dead/closing socket must not break callers
                logger.warning(
                    "Dropping WebSocket for user %s after send failure: %s", user_id, exc
                )
                self.disconnect(user_id, websocket)
        return delivered


# Create a single, global instance of the manager that our app can use
manager = ConnectionManager()
