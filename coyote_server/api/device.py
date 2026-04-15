"""
API router: /api/device — scan, connect, disconnect, status.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from coyote_server.models import (
    ChannelStateResponse,
    ConnectRequest,
    ConnectResponse,
    ScanRequest,
    ScanResponse,
    ScanResultItem,
    StatusResponse,
    ws_battery_event,
    ws_connected_event,
    ws_disconnected_event,
    ws_error_event,
    ws_frame_event,
)
from coyote_server.state import app_state
from coyote_server.ws import ws_manager
from fastapi import APIRouter, HTTPException

from coyopy import CoyoteDevice, DeviceEvent, scan_for_coyote
from coyopy.channel import CoyoteChannel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["device"])


def _channel_state(ch: CoyoteChannel) -> ChannelStateResponse:
    frames = None
    if ch.custom_pattern is not None:
        from coyote_server.models import FrameModel

        frames = [
            FrameModel(
                frequency=frame.frequency,
                amplitude=frame.amplitude,
            )
            for frame in ch.custom_pattern.frames
        ]
    return ChannelStateResponse(
        name=ch.name,
        power_pct=ch.power_pct,
        mode=ch.mode,
        speed=ch.speed,
        frequency=ch.frequency,
        custom_frames=frames,
    )


def _make_device_event_callback(
    device: CoyoteDevice,
) -> Callable[[DeviceEvent, dict[str, Any]], None]:
    """Return a callback that broadcasts device events over WebSocket."""

    _ = device

    def _callback(event: DeviceEvent, data: dict[str, Any]) -> None:
        async def _broadcast() -> None:
            if event == DeviceEvent.CONNECTED:
                payload = ws_connected_event(
                    data.get("address", ""),
                    data.get("battery", 0),
                )
                await ws_manager.broadcast(payload)
            elif event == DeviceEvent.DISCONNECTED:
                await ws_manager.broadcast(ws_disconnected_event())
            elif event == DeviceEvent.BATTERY:
                await ws_manager.broadcast(ws_battery_event(data.get("level", 0)))
            elif event == DeviceEvent.FRAME:
                await ws_manager.broadcast(ws_frame_event(data.get("a", {}), data.get("b", {})))
            elif event == DeviceEvent.ERROR:
                await ws_manager.broadcast(ws_error_event(str(data.get("source", "unknown"))))

        # Schedule broadcast on the running event loop (callback is sync)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_broadcast())
        except RuntimeError:
            pass

    return _callback


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return the current connection status and channel state."""
    dev = app_state.device
    return StatusResponse(
        connected=dev.is_connected,
        address=dev.address,
        battery=dev.battery_level,
        channel_a=_channel_state(dev.channel_a),
        channel_b=_channel_state(dev.channel_b),
    )


@router.post("/scan", response_model=ScanResponse)
async def scan(req: ScanRequest | None = None) -> ScanResponse:
    """Scan for nearby Coyote 3 devices via BLE."""
    req = req or ScanRequest()
    if app_state.device.is_connected:
        raise HTTPException(
            status_code=409,
            detail="Already connected to a device. Disconnect first.",
        )

    try:
        devices = await scan_for_coyote(timeout=req.timeout)
    except Exception as exc:
        log.exception("BLE scan failed")
        raise HTTPException(status_code=500, detail=f"BLE scan failed: {exc}") from exc

    items = [ScanResultItem(address=d.address, name=d.name, rssi=d.rssi) for d in devices]
    app_state.last_scan = [i.model_dump() for i in items]
    return ScanResponse(devices=items)


@router.post("/connect", response_model=ConnectResponse)
async def connect(req: ConnectRequest | None = None) -> ConnectResponse:
    """Connect to a Coyote 3 device.

    If *address* is omitted, uses the first result from the last scan.
    """
    req = req or ConnectRequest()
    if app_state.device.is_connected:
        raise HTTPException(status_code=409, detail="Already connected.")

    address = req.address
    if address is None:
        if not app_state.last_scan:
            raise HTTPException(
                status_code=422,
                detail=("No address provided and no prior scan results available. " "Run /api/scan first."),
            )
        address = app_state.last_scan[0]["address"]

    # Replace the device instance and register the WS broadcast callback
    async with app_state.lock:
        app_state.device = CoyoteDevice()
        app_state.device.on_event(_make_device_event_callback(app_state.device))
        try:
            await app_state.device.connect(address)
        except Exception as exc:
            log.exception("Connection failed")
            raise HTTPException(status_code=500, detail=f"Connection failed: {exc}") from exc

    return ConnectResponse(
        connected=True,
        address=address,
        battery=app_state.device.battery_level,
    )


@router.post("/disconnect")
async def disconnect() -> dict[str, bool]:
    """Disconnect from the current device."""
    if not app_state.device.is_connected:
        raise HTTPException(status_code=409, detail="Not connected.")

    async with app_state.lock:
        try:
            await app_state.device.disconnect()
        except Exception as exc:
            log.exception("Disconnect error")
            raise HTTPException(status_code=500, detail=f"Disconnect error: {exc}") from exc

    return {"disconnected": True}
