"""
Tests for server/models.py — Pydantic request/response models and WS event helpers.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coyote_server.models import (
    ChannelStateResponse,
    ConnectRequest,
    ConnectResponse,
    FrameModel,
    ModeRequest,
    PatternRequest,
    PowerRequest,
    ScanRequest,
    ScanResponse,
    ScanResultItem,
    ws_battery_event,
    ws_connected_event,
    ws_disconnected_event,
    ws_error_event,
    ws_frame_event,
    ws_mode_event,
    ws_power_event,
)

# ---------------------------------------------------------------------------
# ScanRequest
# ---------------------------------------------------------------------------


class TestScanRequest:
    def test_default_timeout(self):
        assert ScanRequest().timeout == 5.0

    def test_timeout_too_low_raises(self):
        with pytest.raises(ValidationError):
            ScanRequest(timeout=0.5)

    def test_timeout_too_high_raises(self):
        with pytest.raises(ValidationError):
            ScanRequest(timeout=60.0)

    def test_valid_boundary_low(self):
        assert ScanRequest(timeout=1.0).timeout == 1.0

    def test_valid_boundary_high(self):
        assert ScanRequest(timeout=30.0).timeout == 30.0


# ---------------------------------------------------------------------------
# PowerRequest
# ---------------------------------------------------------------------------


class TestPowerRequest:
    def test_below_zero_raises(self):
        with pytest.raises(ValidationError):
            PowerRequest(value=-1)

    def test_above_100_raises(self):
        with pytest.raises(ValidationError):
            PowerRequest(value=101)

    def test_zero_is_valid(self):
        assert PowerRequest(value=0).value == 0

    def test_hundred_is_valid(self):
        assert PowerRequest(value=100).value == 100

    def test_midpoint_is_valid(self):
        assert PowerRequest(value=50).value == 50


# ---------------------------------------------------------------------------
# ModeRequest
# ---------------------------------------------------------------------------


class TestModeRequest:
    def test_default_speed_and_frequency(self):
        req = ModeRequest(mode="breath")
        assert req.speed == 1.0
        assert req.frequency == 15

    def test_speed_too_low_raises(self):
        with pytest.raises(ValidationError):
            ModeRequest(mode="breath", speed=0.05)

    def test_speed_too_high_raises(self):
        with pytest.raises(ValidationError):
            ModeRequest(mode="breath", speed=15.0)

    def test_frequency_zero_is_valid(self):
        req = ModeRequest(mode="waves", frequency=0)
        assert req.frequency == 0

    def test_frequency_max_is_valid(self):
        req = ModeRequest(mode="waves", frequency=240)
        assert req.frequency == 240


# ---------------------------------------------------------------------------
# FrameModel
# ---------------------------------------------------------------------------


class TestFrameModel:
    def test_frequency_too_low_raises(self):
        with pytest.raises(ValidationError):
            FrameModel(frequency=5, amplitude=50)

    def test_frequency_too_high_raises(self):
        with pytest.raises(ValidationError):
            FrameModel(frequency=250, amplitude=50)

    def test_amplitude_negative_raises(self):
        with pytest.raises(ValidationError):
            FrameModel(frequency=50, amplitude=-1)

    def test_amplitude_above_100_raises(self):
        with pytest.raises(ValidationError):
            FrameModel(frequency=50, amplitude=101)

    def test_valid_frame(self):
        f = FrameModel(frequency=100, amplitude=50)
        assert f.frequency == 100
        assert f.amplitude == 50

    def test_boundary_values(self):
        f = FrameModel(frequency=10, amplitude=0)
        assert f.frequency == 10
        assert f.amplitude == 0

        f2 = FrameModel(frequency=240, amplitude=100)
        assert f2.frequency == 240
        assert f2.amplitude == 100


# ---------------------------------------------------------------------------
# PatternRequest
# ---------------------------------------------------------------------------


class TestPatternRequest:
    def test_empty_frames_raises(self):
        with pytest.raises(ValidationError):
            PatternRequest(frames=[])

    def test_single_valid_frame_accepted(self):
        req = PatternRequest(frames=[FrameModel(frequency=50, amplitude=50)])
        assert len(req.frames) == 1

    def test_multiple_frames_accepted(self):
        frames = [FrameModel(frequency=f, amplitude=50) for f in [10, 50, 100, 240]]
        req = PatternRequest(frames=frames)
        assert len(req.frames) == 4


# ---------------------------------------------------------------------------
# ConnectRequest
# ---------------------------------------------------------------------------


class TestConnectRequest:
    def test_default_address_is_none(self):
        assert ConnectRequest().address is None

    def test_explicit_address(self):
        req = ConnectRequest(address="AA:BB:CC:DD:EE:FF")
        assert req.address == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# Response models (round-trip construction)
# ---------------------------------------------------------------------------


class TestResponseModels:
    def test_scan_response(self):
        resp = ScanResponse(
            devices=[ScanResultItem(address="AA:BB:CC", name="47L121000", rssi=-50)]
        )
        assert len(resp.devices) == 1

    def test_connect_response(self):
        resp = ConnectResponse(connected=True, address="AA:BB:CC", battery=80)
        assert resp.connected is True

    def test_channel_state_response_defaults(self):
        resp = ChannelStateResponse(name="a", power_pct=0, mode="none")
        assert resp.speed == 1.0
        assert resp.frequency == 15
        assert resp.custom_frames is None


# ---------------------------------------------------------------------------
# WebSocket event helpers
# ---------------------------------------------------------------------------


class TestWSEventHelpers:
    def test_connected_event(self):
        evt = ws_connected_event("AA:BB:CC", 80)
        assert evt["event"] == "connected"
        assert evt["address"] == "AA:BB:CC"
        assert evt["battery"] == 80

    def test_disconnected_event(self):
        evt = ws_disconnected_event()
        assert evt["event"] == "disconnected"

    def test_battery_event(self):
        evt = ws_battery_event(75)
        assert evt["event"] == "battery"
        assert evt["level"] == 75

    def test_power_event(self):
        evt = ws_power_event("a", 50)
        assert evt["event"] == "power"
        assert evt["channel"] == "a"
        assert evt["value"] == 50

    def test_mode_event(self):
        evt = ws_mode_event("b", "breath", speed=1.5, frequency=20)
        assert evt["event"] == "mode"
        assert evt["channel"] == "b"
        assert evt["mode"] == "breath"
        assert evt["speed"] == 1.5
        assert evt["frequency"] == 20

    def test_frame_event(self):
        a = {"frequency": 15, "amplitude": 50}
        b = {"frequency": 20, "amplitude": 30}
        evt = ws_frame_event(a, b)
        assert evt["event"] == "frame"
        assert evt["a"] == a
        assert evt["b"] == b

    def test_error_event(self):
        evt = ws_error_event("something went wrong")
        assert evt["event"] == "error"
        assert evt["detail"] == "something went wrong"
