"""Shared application state for the standalone API server."""

from __future__ import annotations

import asyncio
from typing import Any

from coyopy import CoyoteDevice

from coyote_server.device_manager import DeviceManager


class AppState:
    """Container for mutable server-wide state."""

    def __init__(self) -> None:
        self.device: CoyoteDevice = CoyoteDevice()
        self.lock: asyncio.Lock = asyncio.Lock()
        self.manager: DeviceManager = DeviceManager()
        # Last scan results cached here so the UI can re-read them without
        # triggering another BLE scan.
        self.last_scan: list[dict[str, Any]] = []


# Module-level singleton – imported by all routers.
app_state = AppState()
