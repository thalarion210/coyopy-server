"""Background device manager: auto-scan, connect, and reconnect."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from coyopy import CoyoteDevice, DeviceEvent, scan_for_coyote

log = logging.getLogger(__name__)

SCAN_TIMEOUT = 5.0
SCAN_INTERVAL = 10.0  # seconds between scan attempts
RECONNECT_DELAY = 5.0  # seconds before reconnect after disconnect


class DeviceManager:
    """Automatically scans for a Coyote device, connects, and reconnects.

    The manager runs a background asyncio task that continuously:
    1. Scans for a Coyote BLE device
    2. Connects to the first one found
    3. Waits for disconnection, then repeats

    Call :meth:`pause` to temporarily disable auto-reconnect (e.g. after a
    manual disconnect from the API).  Call :meth:`resume` to re-enable.
    """

    def __init__(self) -> None:
        self._enabled = True
        self._task: asyncio.Task[None] | None = None
        self._disconnected = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background scan/connect loop."""
        self._enabled = True
        self._disconnected.clear()
        self._task = asyncio.create_task(self._loop(), name="device-manager")
        log.info("Device manager started (auto-connect enabled)")

    async def stop(self) -> None:
        """Stop the manager and cancel the background task."""
        self._enabled = False
        self._disconnected.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        log.info("Device manager stopped")

    def pause(self) -> None:
        """Disable auto-reconnect (e.g. after manual disconnect)."""
        self._enabled = False
        self._disconnected.set()
        log.info("Auto-connect paused")

    def resume(self) -> None:
        """Re-enable auto-connect.  Starts the loop if not already running."""
        if self._enabled:
            return
        self._enabled = True
        self._disconnected.clear()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="device-manager")
        log.info("Auto-connect resumed")

    # ------------------------------------------------------------------
    # Device connection helper (shared by auto-loop and manual connect)
    # ------------------------------------------------------------------

    async def connect_device(self, address: str) -> None:
        """Create a fresh :class:`CoyoteDevice`, register callbacks, and connect."""
        from coyote_server.state import app_state

        async with app_state.lock:
            app_state.device = CoyoteDevice()
            app_state.device.on_event(self._on_device_event)
            await app_state.device.connect(address)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_device_event(self, event: DeviceEvent, data: dict[str, Any]) -> None:
        """Handle device events: broadcast via WS and detect disconnects."""
        if event == DeviceEvent.DISCONNECTED:
            self._disconnected.set()

        async def _broadcast() -> None:
            from coyote_server.models import (
                ws_battery_event,
                ws_connected_event,
                ws_disconnected_event,
                ws_error_event,
                ws_frame_event,
            )
            from coyote_server.ws import ws_manager

            if event == DeviceEvent.CONNECTED:
                await ws_manager.broadcast(ws_connected_event(data.get("address", ""), data.get("battery", 0)))
            elif event == DeviceEvent.DISCONNECTED:
                await ws_manager.broadcast(ws_disconnected_event())
            elif event == DeviceEvent.BATTERY:
                await ws_manager.broadcast(ws_battery_event(data.get("level", 0)))
            elif event == DeviceEvent.FRAME:
                await ws_manager.broadcast(ws_frame_event(data.get("a", {}), data.get("b", {})))
            elif event == DeviceEvent.ERROR:
                await ws_manager.broadcast(ws_error_event(str(data.get("source", "unknown"))))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_broadcast())
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        from coyote_server.state import app_state

        log.info("Auto-connect loop started")
        try:
            while self._enabled:
                # If already connected, wait for disconnection
                if app_state.device.is_connected:
                    self._disconnected.clear()
                    await self._disconnected.wait()
                    if not self._enabled:
                        break
                    log.info(
                        "Device disconnected, will attempt reconnect in %.0fs",
                        RECONNECT_DELAY,
                    )
                    await asyncio.sleep(RECONNECT_DELAY)
                    if not self._enabled:
                        break

                # Scan
                log.info("Scanning for Coyote device …")
                try:
                    devices = await scan_for_coyote(timeout=SCAN_TIMEOUT)
                except Exception:
                    log.warning(
                        "BLE scan failed, retrying in %.0fs",
                        SCAN_INTERVAL,
                        exc_info=True,
                    )
                    await asyncio.sleep(SCAN_INTERVAL)
                    continue

                if not devices:
                    log.info("No devices found, retrying in %.0fs", SCAN_INTERVAL)
                    await asyncio.sleep(SCAN_INTERVAL)
                    continue

                # Cache scan results
                from coyote_server.models import ScanResultItem

                app_state.last_scan = [
                    ScanResultItem(address=d.address, name=d.name, rssi=d.rssi).model_dump() for d in devices
                ]

                # Connect to the strongest device
                target = devices[0]
                log.info("Found device %s (RSSI %d), connecting …", target.address, target.rssi)
                try:
                    await self.connect_device(target.address)
                    log.info("Auto-connected to %s", target.address)
                except Exception:
                    log.warning(
                        "Connection to %s failed, retrying in %.0fs",
                        target.address,
                        SCAN_INTERVAL,
                        exc_info=True,
                    )
                    await asyncio.sleep(SCAN_INTERVAL)
        except asyncio.CancelledError:
            log.info("Auto-connect loop cancelled")
        except Exception:
            log.exception("Unexpected error in auto-connect loop")
        finally:
            log.info("Auto-connect loop exited")
