# backend/app/core/ws_manager.py

import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # user_id -> every live socket for that user (several tabs/devices).
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """Accepts a new WebSocket connection and stores it."""
        await websocket.accept()
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

    async def send_personal_message(self, message: dict, user_id: int):
        """Send a JSON message to all of a user's sockets. Never raises."""
        for websocket in list(self.active_connections.get(user_id, [])):
            try:
                await websocket.send_json(message)
            except Exception as exc:  # dead/closing socket must not break callers
                logger.warning(
                    "Dropping WebSocket for user %s after send failure: %s", user_id, exc
                )
                self.disconnect(user_id, websocket)


# Create a single, global instance of the manager that our app can use
manager = ConnectionManager()
