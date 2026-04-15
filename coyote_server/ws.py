"""
WebSocket connection manager.

Maintains the set of active WebSocket connections and provides a
broadcast helper that sends a JSON-serialisable dict to all of them.

The manager is a module-level singleton so that the device event callback
(installed at startup) can reach all connected browser sessions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        log.debug("WS client connected (total: %d)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass
        log.debug("WS client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send *data* as JSON to every connected WebSocket client.

        Clients that fail to receive the message are silently removed.
        """
        if not self._connections:
            return

        message = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                log.debug("WS send failed – removing client", exc_info=True)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Module-level singleton
ws_manager = ConnectionManager()
