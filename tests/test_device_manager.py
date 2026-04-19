"""Tests for coyote_server/device_manager.py."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from coyopy.scanner import DiscoveredDevice

from coyote_server.device_manager import DeviceManager


def _make_state(connected: bool = False) -> SimpleNamespace:
    device = SimpleNamespace(
        is_connected=connected,
        on_event=MagicMock(),
    )
    return SimpleNamespace(
        device=device,
        last_scan=[],
        lock=asyncio.Lock(),
    )


# ------------------------------------------------------------------
# start / stop / pause / resume
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestLifecycle:
    async def test_start_creates_task(self) -> None:
        mgr = DeviceManager()
        state = _make_state()
        with patch("coyote_server.state.app_state", state):
            await mgr.start()
        assert mgr.enabled is True
        assert mgr._task is not None
        assert not mgr._task.done()
        await mgr.stop()

    async def test_stop_cancels_task(self) -> None:
        mgr = DeviceManager()
        state = _make_state()
        with patch("coyote_server.state.app_state", state):
            await mgr.start()
            await mgr.stop()
        assert mgr.enabled is False
        assert mgr._task is None

    async def test_stop_when_not_started(self) -> None:
        mgr = DeviceManager()
        await mgr.stop()
        assert mgr._task is None

    async def test_pause_disables(self) -> None:
        mgr = DeviceManager()
        mgr.pause()
        assert mgr.enabled is False
        assert mgr._disconnected.is_set()

    async def test_resume_when_already_enabled(self) -> None:
        mgr = DeviceManager()
        mgr._enabled = True
        mgr.resume()  # should be a no-op
        assert mgr._task is None

    async def test_resume_starts_loop(self) -> None:
        mgr = DeviceManager()
        state = _make_state()
        mgr.pause()
        with patch("coyote_server.state.app_state", state):
            mgr.resume()
        assert mgr.enabled is True
        assert mgr._task is not None
        await mgr.stop()


# ------------------------------------------------------------------
# connect_device
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectDevice:
    async def test_connect_device_creates_and_connects(self) -> None:
        mgr = DeviceManager()
        state = _make_state()
        fake_device = MagicMock()
        fake_device.on_event = MagicMock()
        fake_device.connect = AsyncMock()

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.CoyoteDevice", return_value=fake_device),
        ):
            await mgr.connect_device("AA:BB")

        fake_device.on_event.assert_called_once_with(mgr._on_device_event)
        fake_device.connect.assert_awaited_once_with("AA:BB")
        assert state.device is fake_device


# ------------------------------------------------------------------
# _loop
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoop:
    async def test_loop_scans_and_connects(self) -> None:
        """Loop finds a device, connects, then exits when disabled."""
        mgr = DeviceManager()
        state = _make_state(connected=False)

        found = [DiscoveredDevice(address="DD:EE", name="47L121000", rssi=-40)]

        call_count = 0

        async def _fake_connect(address: str) -> None:
            nonlocal call_count
            call_count += 1
            state.device.is_connected = True
            # Simulate: after connect, pause to exit the loop
            mgr.pause()

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(return_value=found)),
        ):
            mgr.connect_device = AsyncMock(side_effect=_fake_connect)  # type: ignore[assignment]
            await mgr._loop()

        assert call_count == 1
        assert len(state.last_scan) == 1
        assert state.last_scan[0]["address"] == "DD:EE"

    async def test_loop_retries_on_scan_failure(self) -> None:
        """Loop retries after BLE scan error, then exits."""
        mgr = DeviceManager()
        state = _make_state(connected=False)

        call_count = 0

        async def _scan(timeout: float = 5.0) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("ble down")
            mgr.pause()  # stop after second call
            return []

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(side_effect=_scan)),
            patch("coyote_server.device_manager.SCAN_INTERVAL", 0),
        ):
            await mgr._loop()

        assert call_count == 2

    async def test_loop_retries_on_empty_scan(self) -> None:
        """Loop retries when scan returns no devices."""
        mgr = DeviceManager()
        state = _make_state(connected=False)

        call_count = 0

        async def _scan(timeout: float = 5.0) -> list:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mgr.pause()
            return []

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(side_effect=_scan)),
            patch("coyote_server.device_manager.SCAN_INTERVAL", 0),
        ):
            await mgr._loop()

        assert call_count == 2

    async def test_loop_retries_on_connect_failure(self) -> None:
        """Loop retries when connection fails."""
        mgr = DeviceManager()
        state = _make_state(connected=False)

        found = [DiscoveredDevice(address="FF:00", name="47L121000", rssi=-50)]

        call_count = 0

        async def _connect(address: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("connect failed")
            mgr.pause()

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(return_value=found)),
            patch("coyote_server.device_manager.SCAN_INTERVAL", 0),
        ):
            mgr.connect_device = AsyncMock(side_effect=_connect)  # type: ignore[assignment]
            await mgr._loop()

        assert call_count == 2

    async def test_loop_waits_for_disconnect_then_reconnects(self) -> None:
        """When connected, loop waits for disconnect event then rescans."""
        mgr = DeviceManager()
        state = _make_state(connected=True)

        found = [DiscoveredDevice(address="AA:BB", name="47L121000", rssi=-60)]

        ran_reconnect = False

        async def _connect(address: str) -> None:
            nonlocal ran_reconnect
            ran_reconnect = True
            state.device.is_connected = True
            mgr.pause()

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(return_value=found)),
            patch("coyote_server.device_manager.RECONNECT_DELAY", 0),
        ):
            mgr.connect_device = AsyncMock(side_effect=_connect)  # type: ignore[assignment]

            async def _trigger_disconnect() -> None:
                await asyncio.sleep(0.01)
                state.device.is_connected = False
                mgr._disconnected.set()

            asyncio.create_task(_trigger_disconnect())
            await mgr._loop()

        assert ran_reconnect is True

    async def test_loop_exits_on_cancel(self) -> None:
        mgr = DeviceManager()
        state = _make_state(connected=False)

        async def _hang(timeout: float = 5.0) -> list:
            await asyncio.sleep(100)
            return []

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.scan_for_coyote", new=AsyncMock(side_effect=_hang)),
        ):
            await mgr.start()
            await asyncio.sleep(0.01)
            await mgr.stop()

    async def test_loop_exits_if_disabled_after_disconnect_wait(self) -> None:
        """If disabled while waiting for disconnect, loop exits cleanly."""
        mgr = DeviceManager()
        state = _make_state(connected=True)

        with patch("coyote_server.state.app_state", state):

            async def _disable() -> None:
                await asyncio.sleep(0.01)
                mgr.pause()

            asyncio.create_task(_disable())
            await mgr._loop()

    async def test_loop_exits_if_disabled_after_reconnect_delay(self) -> None:
        """If disabled during reconnect delay, loop exits cleanly."""
        mgr = DeviceManager()
        state = _make_state(connected=True)

        with (
            patch("coyote_server.state.app_state", state),
            patch("coyote_server.device_manager.RECONNECT_DELAY", 0),
        ):
            # Immediately set disconnected + disable after reconnect delay
            mgr._disconnected.set()

            async def _disable() -> None:
                await asyncio.sleep(0.01)
                mgr.pause()

            asyncio.create_task(_disable())
            # After disconnect wait, the reconnect sleep(0) passes,
            # then the _enabled check at top of while will break.
            # But we need to ensure _enabled becomes False.
            # Let's just directly set it to simulate the timing.
            state.device.is_connected = True  # enter the wait branch
            mgr._enabled = True  # still enabled at start

            async def _trigger() -> None:
                await asyncio.sleep(0)
                state.device.is_connected = False
                mgr._disconnected.set()
                await asyncio.sleep(0)
                mgr._enabled = False

            mgr._disconnected.clear()
            asyncio.create_task(_trigger())
            await mgr._loop()
