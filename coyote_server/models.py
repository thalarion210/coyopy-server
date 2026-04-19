"""
Pydantic request and response models for the REST API.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

ChannelName = Literal["a", "b"]
ModeName = Literal["none", "breath", "waves", "climb", "reverse_climb", "toggle", "tease", "custom"]


# ---------------------------------------------------------------------------
# Device endpoint models
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    timeout: float = Field(default=5.0, ge=1.0, le=30.0, description="Scan duration in seconds")


class ScanResultItem(BaseModel):
    address: str
    name: str
    rssi: int


class ScanResponse(BaseModel):
    devices: list[ScanResultItem]


class ConnectRequest(BaseModel):
    address: str | None = Field(
        default=None,
        description="BLE address to connect to. If omitted, connects to the first scanned device.",
    )


class ConnectResponse(BaseModel):
    connected: bool
    address: str
    battery: int


class StatusResponse(BaseModel):
    connected: bool
    address: str | None
    battery: int
    auto_connect: bool
    channel_a: ChannelStateResponse
    channel_b: ChannelStateResponse


# ---------------------------------------------------------------------------
# Channel endpoint models
# ---------------------------------------------------------------------------


class FrameModel(BaseModel):
    frequency: int = Field(ge=10, le=240, description="Frequency, 10–240")
    amplitude: int = Field(ge=0, le=100, description="Amplitude, 0–100")


class ChannelStateResponse(BaseModel):
    name: str
    power_pct: int
    mode: str
    speed: float = 1.0
    frequency: int = 15
    custom_frames: list[FrameModel] | None = None


class PowerRequest(BaseModel):
    value: int = Field(ge=0, le=100, description="Desired power 0–100 %")


class ModeRequest(BaseModel):
    mode: ModeName
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Speed multiplier (>1 faster, <1 slower)",
    )
    frequency: int = Field(
        default=15,
        ge=0,
        le=240,
        description="Base frequency in Hz (10-240); 0 = dynamic",
    )


class PatternRequest(BaseModel):
    frames: list[FrameModel] = Field(
        min_length=1,
        max_length=1024,
        description="Ordered list of waveform frames; will loop continuously.",
    )


class AutoConnectRequest(BaseModel):
    enabled: bool = Field(description="Whether to enable automatic scanning and reconnection.")


class AutoConnectResponse(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# WebSocket event models (serialised as plain dicts for simplicity)
# ---------------------------------------------------------------------------


def ws_connected_event(address: str, battery: int) -> dict[str, Any]:
    return {"event": "connected", "address": address, "battery": battery}


def ws_disconnected_event() -> dict[str, Any]:
    return {"event": "disconnected"}


def ws_battery_event(level: int) -> dict[str, Any]:
    return {"event": "battery", "level": level}


def ws_power_event(channel: str, value: int) -> dict[str, Any]:
    return {"event": "power", "channel": channel, "value": value}


def ws_mode_event(
    channel: str,
    mode: str,
    speed: float = 1.0,
    frequency: int = 10,
) -> dict[str, Any]:
    return {
        "event": "mode",
        "channel": channel,
        "mode": mode,
        "speed": speed,
        "frequency": frequency,
    }


def ws_frame_event(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"event": "frame", "a": a, "b": b}


def ws_error_event(detail: str) -> dict[str, Any]:
    return {"event": "error", "detail": detail}
