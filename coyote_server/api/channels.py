"""
API router: /api/channel/{ch} — power, mode, custom pattern.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from coyopy import CoyoteFrame, CustomPattern
from coyopy.channel import CoyoteChannel
from fastapi import APIRouter, HTTPException, Path

from coyote_server.models import (
    ChannelStateResponse,
    FrameModel,
    ModeRequest,
    PatternRequest,
    PowerRequest,
    ws_mode_event,
    ws_power_event,
)
from coyote_server.state import app_state
from coyote_server.ws import ws_manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channel", tags=["channels"])

_VALID_CHANNELS = {"a", "b"}


def _get_channel(ch: str) -> CoyoteChannel:
    if ch not in _VALID_CHANNELS:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{ch}'. Use 'a' or 'b'.")
    if not app_state.device.is_connected:
        raise HTTPException(status_code=409, detail="Not connected to a device.")
    return app_state.device.channel_a if ch == "a" else app_state.device.channel_b


def _channel_response(ch: CoyoteChannel) -> ChannelStateResponse:
    frames = None
    if ch.custom_pattern is not None:
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


def _broadcast(data: dict[str, Any]) -> None:
    """Fire-and-forget broadcast from a sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_manager.broadcast(data))
    except RuntimeError:
        pass


@router.get("/{ch}", response_model=ChannelStateResponse)
async def get_channel(
    ch: str = Path(description="Channel name: 'a' or 'b'"),
) -> ChannelStateResponse:
    """Get current state of a channel."""
    channel = _get_channel(ch)
    return _channel_response(channel)


@router.put("/{ch}/power", response_model=ChannelStateResponse)
async def set_power(
    req: PowerRequest,
    ch: str = Path(description="Channel name: 'a' or 'b'"),
) -> ChannelStateResponse:
    """Set output power for a channel (0–100 %)."""
    channel = _get_channel(ch)
    channel.set_power(req.value)
    _broadcast(ws_power_event(ch, channel.power_pct))
    return _channel_response(channel)


@router.put("/{ch}/mode", response_model=ChannelStateResponse)
async def set_mode(
    req: ModeRequest,
    ch: str = Path(description="Channel name: 'a' or 'b'"),
) -> ChannelStateResponse:
    """Set the waveform mode for a channel."""
    channel = _get_channel(ch)
    try:
        channel.set_mode(req.mode, speed=req.speed, frequency=req.frequency)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _broadcast(ws_mode_event(ch, channel.mode, channel.speed, channel.frequency))
    return _channel_response(channel)


@router.put("/{ch}/pattern", response_model=ChannelStateResponse)
async def set_pattern(
    req: PatternRequest,
    ch: str = Path(description="Channel name: 'a' or 'b'"),
) -> ChannelStateResponse:
    """Install a custom waveform pattern and switch the channel to custom mode."""
    channel = _get_channel(ch)
    try:
        frames = [CoyoteFrame(frequency=f.frequency, amplitude=f.amplitude) for f in req.frames]
        pattern = CustomPattern(frames=frames)
        channel.set_custom_pattern(pattern)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _broadcast(ws_mode_event(ch, channel.mode, channel.speed, channel.frequency))
    return _channel_response(channel)
