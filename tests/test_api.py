"""
Tests for server/api/channels.py and server/api/device.py REST endpoints.

Uses FastAPI's TestClient with a minimal app that includes only the two
routers under test.  The device-level BLE operations are mocked so no
Bluetooth hardware is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from coyopy.channel import CoyoteChannel
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coyote_server.api.channels import router as channels_router
from coyote_server.api.device import router as device_router

# ---------------------------------------------------------------------------
# Minimal test application
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(channels_router)
_app.include_router(device_router)


def _make_mock_device(connected: bool = True) -> MagicMock:
    dev = MagicMock()
    dev.is_connected = connected
    dev.address = "AA:BB:CC:DD:EE:FF" if connected else None
    dev.battery_level = 80 if connected else 0
    dev.channel_a = CoyoteChannel("a")
    dev.channel_b = CoyoteChannel("b")
    return dev


# ---------------------------------------------------------------------------
# Channel API — error paths (no mock needed, default state is disconnected)
# ---------------------------------------------------------------------------


class TestChannelApiErrors:
    def setup_method(self):
        self.client = TestClient(_app)

    def test_invalid_channel_returns_404(self):
        resp = self.client.get("/api/channel/x")
        assert resp.status_code == 404

    def test_get_channel_a_when_disconnected_returns_409(self):
        resp = self.client.get("/api/channel/a")
        assert resp.status_code == 409

    def test_set_power_when_disconnected_returns_409(self):
        resp = self.client.put("/api/channel/a/power", json={"value": 50})
        assert resp.status_code == 409

    def test_set_mode_when_disconnected_returns_409(self):
        resp = self.client.put("/api/channel/a/mode", json={"mode": "breath"})
        assert resp.status_code == 409

    def test_set_pattern_when_disconnected_returns_409(self):
        resp = self.client.put(
            "/api/channel/a/pattern",
            json={"frames": [{"frequency": 50, "amplitude": 50}]},
        )
        assert resp.status_code == 409

    def test_set_power_invalid_value_returns_422(self):
        resp = self.client.put("/api/channel/a/power", json={"value": 200})
        assert resp.status_code == 422

    def test_set_pattern_empty_frames_returns_422(self):
        resp = self.client.put("/api/channel/a/pattern", json={"frames": []})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Channel API — success paths (patched connected device)
# ---------------------------------------------------------------------------


@pytest.fixture()
def channel_client():
    """TestClient with a mocked connected device injected into the channel router."""
    mock_device = _make_mock_device(connected=True)
    mock_state = MagicMock()
    mock_state.device = mock_device

    with patch("coyote_server.api.channels.app_state", mock_state):
        yield TestClient(_app), mock_device


class TestChannelApiSuccess:
    def test_get_channel_a_returns_200(self, channel_client):
        client, _ = channel_client
        resp = client.get("/api/channel/a")
        assert resp.status_code == 200

    def test_get_channel_b_returns_200(self, channel_client):
        client, _ = channel_client
        resp = client.get("/api/channel/b")
        assert resp.status_code == 200

    def test_get_channel_response_shape(self, channel_client):
        client, _ = channel_client
        data = client.get("/api/channel/a").json()
        assert data["name"] == "a"
        assert "power_pct" in data
        assert "mode" in data

    def test_set_power_updates_channel(self, channel_client):
        client, device = channel_client
        resp = client.put("/api/channel/a/power", json={"value": 42})
        assert resp.status_code == 200
        assert device.channel_a.power_pct == 42

    def test_set_power_returns_updated_state(self, channel_client):
        client, _ = channel_client
        data = client.put("/api/channel/a/power", json={"value": 75}).json()
        assert data["power_pct"] == 75

    def test_set_mode_updates_channel(self, channel_client):
        client, device = channel_client
        resp = client.put("/api/channel/b/mode", json={"mode": "breath"})
        assert resp.status_code == 200
        assert device.channel_b.mode == "breath"

    def test_set_pattern_switches_to_custom_mode(self, channel_client):
        client, device = channel_client
        frames = [{"frequency": 50, "amplitude": 50}, {"frequency": 100, "amplitude": 25}]
        resp = client.put("/api/channel/a/pattern", json={"frames": frames})
        assert resp.status_code == 200
        assert device.channel_a.mode == "custom"
        assert device.channel_a.custom_pattern is not None


# ---------------------------------------------------------------------------
# Device API — /api/status (no BLE required)
# ---------------------------------------------------------------------------


class TestDeviceStatus:
    def setup_method(self):
        self.client = TestClient(_app)

    def test_status_returns_200(self):
        resp = self.client.get("/api/status")
        assert resp.status_code == 200

    def test_status_connected_false_when_disconnected(self):
        data = self.client.get("/api/status").json()
        assert data["connected"] is False
        assert data["address"] is None
        assert data["battery"] == 0

    def test_status_includes_channel_state(self):
        data = self.client.get("/api/status").json()
        assert "channel_a" in data
        assert "channel_b" in data
        assert data["channel_a"]["name"] == "a"
        assert data["channel_b"]["name"] == "b"


class TestDeviceStatusConnected:
    def test_status_when_connected(self):
        mock_device = _make_mock_device(connected=True)
        mock_state = MagicMock()
        mock_state.device = mock_device

        with patch("coyote_server.api.device.app_state", mock_state):
            client = TestClient(_app)
            data = client.get("/api/status").json()

        assert data["connected"] is True
        assert data["address"] == "AA:BB:CC:DD:EE:FF"
        assert data["battery"] == 80


# ---------------------------------------------------------------------------
# Device API — error paths for scan / connect / disconnect
# ---------------------------------------------------------------------------


class TestDeviceApiErrors:
    def setup_method(self):
        self.client = TestClient(_app)

    def test_disconnect_when_not_connected_returns_409(self):
        resp = self.client.post("/api/disconnect")
        assert resp.status_code == 409

    def test_connect_without_address_and_no_scan_returns_422(self):
        """No address supplied and last_scan is empty → 422."""
        mock_state = MagicMock()
        mock_state.device.is_connected = False
        mock_state.last_scan = []

        with patch("coyote_server.api.device.app_state", mock_state):
            client = TestClient(_app)
            resp = client.post("/api/connect", json={})
        assert resp.status_code == 422

    def test_scan_when_already_connected_returns_409(self):
        mock_state = MagicMock()
        mock_state.device.is_connected = True

        with patch("coyote_server.api.device.app_state", mock_state):
            client = TestClient(_app)
            resp = client.post("/api/scan", json={"timeout": 5.0})
        assert resp.status_code == 409

    def test_connect_when_already_connected_returns_409(self):
        mock_state = MagicMock()
        mock_state.device.is_connected = True

        with patch("coyote_server.api.device.app_state", mock_state):
            client = TestClient(_app)
            resp = client.post("/api/connect", json={})
        assert resp.status_code == 409
