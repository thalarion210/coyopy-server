"""
API router: /api/device — scan, connect, disconnect, status.
"""

from __future__ import annotations

import logging

from coyopy import scan_for_coyote
from coyopy.channel import CoyoteChannel
from fastapi import APIRouter, HTTPException

from coyote_server.models import (
    AutoConnectRequest,
    AutoConnectResponse,
    ChannelStateResponse,
    ConnectRequest,
    ConnectResponse,
    ScanRequest,
    ScanResponse,
    ScanResultItem,
    StatusResponse,
)
from coyote_server.state import app_state

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


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return the current connection status and channel state."""
    dev = app_state.device
    return StatusResponse(
        connected=dev.is_connected,
        address=dev.address,
        battery=dev.battery_level,
        auto_connect=app_state.manager.enabled,
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

    # Pause auto-connect while connecting manually
    app_state.manager.pause()
    try:
        await app_state.manager.connect_device(address)
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
    """Disconnect from the current device.

    Also pauses auto-reconnect.  Call ``POST /api/auto-connect`` with
    ``{"enabled": true}`` to re-enable it.
    """
    if not app_state.device.is_connected:
        raise HTTPException(status_code=409, detail="Not connected.")

    app_state.manager.pause()
    async with app_state.lock:
        try:
            await app_state.device.disconnect()
        except Exception as exc:
            log.exception("Disconnect error")
            raise HTTPException(status_code=500, detail=f"Disconnect error: {exc}") from exc

    return {"disconnected": True}


@router.post("/auto-connect", response_model=AutoConnectResponse)
async def auto_connect(req: AutoConnectRequest) -> AutoConnectResponse:
    """Enable or disable automatic device scanning and reconnection."""
    if req.enabled:
        app_state.manager.resume()
    else:
        app_state.manager.pause()
    return AutoConnectResponse(enabled=app_state.manager.enabled)
