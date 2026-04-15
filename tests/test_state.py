"""Tests for coyote_server/state.py."""

from __future__ import annotations

import asyncio

from coyote_server.state import AppState

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestAppStateInit:
    def test_device_not_connected_initially(self):
        state = AppState()
        assert not state.device.is_connected

    def test_last_scan_empty_initially(self):
        state = AppState()
        assert state.last_scan == []

    def test_has_asyncio_lock(self):
        state = AppState()
        assert isinstance(state.lock, asyncio.Lock)

    def test_device_has_channels(self):
        state = AppState()
        assert state.device.channel_a is not None
        assert state.device.channel_b is not None
