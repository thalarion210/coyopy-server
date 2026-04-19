"""FastAPI application entry point for the standalone server project."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from coyote_server import __version__
from coyote_server.api.channels import router as channels_router
from coyote_server.api.device import router as device_router
from coyote_server.ws import ws_manager

log = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup / shutdown hooks."""
    del app
    log.info("Coyote server starting up")
    from coyote_server.state import app_state

    auto_connect = os.getenv("COYOTE_AUTO_CONNECT", "true").lower() in {"1", "true", "yes", "on"}
    if auto_connect:
        await app_state.manager.start()
    else:
        app_state.manager.pause()
        log.info("Auto-connect disabled via COYOTE_AUTO_CONNECT")
    yield
    # Stop the device manager and disconnect cleanly
    await app_state.manager.stop()
    if app_state.device.is_connected:
        log.info("Disconnecting device on shutdown …")
        try:
            await app_state.device.disconnect()
        except Exception:
            log.warning("Error during shutdown disconnect", exc_info=True)
    log.info("Coyote server shut down")


app = FastAPI(
    title="Coyote Server",
    description="REST API and lightweight control UI for the DG-Labs Coyote",
    version=__version__,
    lifespan=lifespan,
)

# Default to local browser clients. This can be tightened further for remote deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(device_router)
app.include_router(channels_router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    # Send the current status immediately so the client can sync its UI
    from coyote_server.models import ws_connected_event, ws_disconnected_event
    from coyote_server.state import app_state

    dev = app_state.device
    if dev.is_connected:
        await ws.send_json(ws_connected_event(dev.address or "", dev.battery_level))
    else:
        await ws.send_json(ws_disconnected_event())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict):
                    await _handle_ws_message(msg)
            except Exception:
                log.debug("Unhandled WS message", exc_info=True)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)


async def _handle_ws_message(msg: dict[str, Any]) -> None:
    """Handle optional inbound WebSocket messages from clients.

    The standalone server uses the WebSocket primarily for outbound device
    events. Unsupported inbound messages are ignored deliberately.
    """

    msg_type = msg.get("type")
    if not isinstance(msg_type, str):
        return
    log.debug("Ignoring unsupported WS message type %s", msg_type)


# ---------------------------------------------------------------------------
# Static files (web front-end)
# ---------------------------------------------------------------------------

if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
else:
    log.warning("web/ directory not found at %s – UI will not be available", _WEB_DIR)


# ---------------------------------------------------------------------------
# Entry point for the coyopy-server console script
# ---------------------------------------------------------------------------


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    host = os.getenv("COYOTE_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("COYOTE_SERVER_PORT", "8000"))
    reload_enabled = os.getenv("COYOTE_SERVER_RELOAD", "false").lower() in {"1", "true", "yes", "on"}
    uvicorn.run("coyote_server.main:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    run()
