"""
Additional tests for server/api/channels.py and server/api/device.py.

Focus: previously uncovered exception and callback branches.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from coyopy import DeviceEvent
from coyopy.channel import CoyoteChannel
from coyopy.scanner import DiscoveredDevice
from fastapi import FastAPI
from fastapi.testclient import TestClient

import coyote_server.api.channels as channels_api
import coyote_server.api.device as device_api
from coyote_server.api.channels import router as channels_router
from coyote_server.api.device import router as device_router
from coyote_server.device_manager import DeviceManager


class FakeDevice:
    def __init__(self, connected: bool = False, *, connect_error: Exception | None = None):
        self.is_connected = connected
        self.address = "AA:BB:CC:DD:EE:FF" if connected else None
        self.battery_level = 50 if connected else 0
        self.channel_a = CoyoteChannel("a")
        self.channel_b = CoyoteChannel("b")
        self._connect_error = connect_error
        self._cb = None

    async def connect(self, address: str) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self.is_connected = True
        self.address = address
        self.battery_level = 77

    async def disconnect(self) -> None:
        self.is_connected = False

    def on_event(self, callback) -> None:
        self._cb = callback


class FakeManager:
    def __init__(self) -> None:
        self.enabled = True

    def pause(self) -> None:
        self.enabled = False

    def resume(self) -> None:
        self.enabled = True

    async def connect_device(self, address: str) -> None:
        pass  # overridden per-test via patching


def _make_state(device) -> SimpleNamespace:
    return SimpleNamespace(
        device=device,
        last_scan=[],
        lock=asyncio.Lock(),
        manager=FakeManager(),
    )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(device_router)
    app.include_router(channels_router)
    return TestClient(app)


class TestChannelBranches:
    def test_set_mode_value_error_returns_422(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=True))
        state.device.channel_a.set_mode = MagicMock(side_effect=ValueError("bad mode"))

        with patch.object(channels_api, "app_state", state):
            resp = client.put(
                "/api/channel/a/mode",
                json={"mode": "breath", "speed": 1.0, "frequency": 15},
            )

        assert resp.status_code == 422
        assert "bad mode" in resp.text

    def test_set_pattern_value_error_returns_422(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=True))
        state.device.channel_a.set_custom_pattern = MagicMock(side_effect=ValueError("bad pattern"))

        with patch.object(channels_api, "app_state", state):
            resp = client.put(
                "/api/channel/a/pattern",
                json={"frames": [{"frequency": 20, "amplitude": 50}]},
            )

        assert resp.status_code == 422
        assert "bad pattern" in resp.text

    def test_broadcast_ignores_runtime_error(self):
        with patch.object(
            channels_api.asyncio,
            "get_event_loop",
            side_effect=RuntimeError("no loop"),
        ):
            channels_api._broadcast({"event": "x"})

    def test_broadcast_no_task_when_loop_not_running(self):
        loop = MagicMock()
        loop.is_running.return_value = False

        with patch.object(channels_api.asyncio, "get_event_loop", return_value=loop):
            channels_api._broadcast({"event": "x"})

        loop.create_task.assert_not_called()


class TestDeviceApiBranches:
    def test_scan_success_updates_last_scan(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=False))

        devices = [DiscoveredDevice(address="AA", name="47L121000", rssi=-55)]
        with (
            patch.object(device_api, "app_state", state),
            patch.object(device_api, "scan_for_coyote", new=AsyncMock(return_value=devices)),
        ):
            resp = client.post("/api/scan", json={"timeout": 2.0})

        assert resp.status_code == 200
        assert len(state.last_scan) == 1
        assert state.last_scan[0]["address"] == "AA"

    def test_scan_failure_returns_500(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=False))

        with (
            patch.object(device_api, "app_state", state),
            patch.object(device_api, "scan_for_coyote", new=AsyncMock(side_effect=RuntimeError("ble down"))),
        ):
            resp = client.post("/api/scan", json={"timeout": 2.0})

        assert resp.status_code == 500
        assert "BLE scan failed" in resp.text

    def test_connect_success_uses_last_scan_if_address_missing(self):
        client = _build_client()
        fake_dev = FakeDevice(connected=False)
        state = _make_state(fake_dev)
        state.last_scan = [{"address": "CC:DD"}]

        async def _connect(address: str) -> None:
            fake_dev.is_connected = True
            fake_dev.address = address
            fake_dev.battery_level = 77

        state.manager.connect_device = AsyncMock(side_effect=_connect)

        with patch.object(device_api, "app_state", state):
            resp = client.post("/api/connect", json={})

        assert resp.status_code == 200
        assert resp.json()["address"] == "CC:DD"
        state.manager.connect_device.assert_awaited_once_with("CC:DD")

    def test_connect_failure_returns_500(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=False))
        state.manager.connect_device = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(device_api, "app_state", state):
            resp = client.post("/api/connect", json={"address": "AA:BB"})

        assert resp.status_code == 500
        assert "Connection failed" in resp.text

    def test_disconnect_success_returns_true(self):
        client = _build_client()
        dev = FakeDevice(connected=True)
        state = _make_state(dev)

        with patch.object(device_api, "app_state", state):
            resp = client.post("/api/disconnect")

        assert resp.status_code == 200
        assert resp.json() == {"disconnected": True}

    def test_disconnect_failure_returns_500(self):
        client = _build_client()
        state = _make_state(FakeDevice(connected=True))
        state.device.disconnect = AsyncMock(side_effect=RuntimeError("cannot disconnect"))

        with patch.object(device_api, "app_state", state):
            resp = client.post("/api/disconnect")

        assert resp.status_code == 500
        assert "Disconnect error" in resp.text


@pytest.mark.asyncio
class TestDeviceCallbackBranches:
    async def test_callback_connected_event(self):
        mgr = DeviceManager()
        with patch("coyote_server.ws.ws_manager", MagicMock(broadcast=AsyncMock())) as ws:
            mgr._on_device_event(DeviceEvent.CONNECTED, {"address": "AA", "battery": 88})
            await asyncio.sleep(0)
        ws.broadcast.assert_awaited_once()

    async def test_callback_disconnected_event(self):
        mgr = DeviceManager()
        with patch("coyote_server.ws.ws_manager", MagicMock(broadcast=AsyncMock())) as ws:
            mgr._on_device_event(DeviceEvent.DISCONNECTED, {})
            await asyncio.sleep(0)
        ws.broadcast.assert_awaited_once()
        assert mgr._disconnected.is_set()

    async def test_callback_battery_event(self):
        mgr = DeviceManager()
        with patch("coyote_server.ws.ws_manager", MagicMock(broadcast=AsyncMock())) as ws:
            mgr._on_device_event(DeviceEvent.BATTERY, {"level": 42})
            await asyncio.sleep(0)
        ws.broadcast.assert_awaited_once()

    async def test_callback_frame_event(self):
        mgr = DeviceManager()
        with patch("coyote_server.ws.ws_manager", MagicMock(broadcast=AsyncMock())) as ws:
            mgr._on_device_event(DeviceEvent.FRAME, {"a": {"x": 1}, "b": {"y": 2}})
            await asyncio.sleep(0)
        ws.broadcast.assert_awaited_once()

    async def test_callback_error_event(self):
        mgr = DeviceManager()
        with patch("coyote_server.ws.ws_manager", MagicMock(broadcast=AsyncMock())) as ws:
            mgr._on_device_event(DeviceEvent.ERROR, {"source": "test"})
            await asyncio.sleep(0)
        ws.broadcast.assert_awaited_once()

    async def test_callback_ignores_runtime_error_get_event_loop(self):
        mgr = DeviceManager()
        with patch(
            "asyncio.get_event_loop",
            side_effect=RuntimeError("no loop"),
        ):
            mgr._on_device_event(DeviceEvent.CONNECTED, {"address": "AA", "battery": 1})
