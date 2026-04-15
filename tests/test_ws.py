"""
Tests for server/ws.py — ConnectionManager.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from coyote_server.ws import ConnectionManager


def _make_ws() -> MagicMock:
    """Return a mock WebSocket with async accept/send_text methods."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnect:
    async def test_accept_is_called(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)
        ws.accept.assert_called_once()

    async def test_client_count_increases(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)
        assert mgr.client_count == 1

    async def test_multiple_clients(self):
        mgr = ConnectionManager()
        for _ in range(3):
            await mgr.connect(_make_ws())
        assert mgr.client_count == 3


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert mgr.client_count == 0

    def test_disconnect_unknown_does_not_raise(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        mgr.disconnect(ws)  # never connected — must not raise

    @pytest.mark.asyncio
    async def test_disconnect_only_removes_target(self):
        mgr = ConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        mgr.disconnect(ws1)
        assert mgr.client_count == 1


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBroadcast:
    async def test_broadcast_with_no_clients_does_not_raise(self):
        mgr = ConnectionManager()
        await mgr.broadcast({"event": "test"})  # must not raise

    async def test_broadcast_sends_json_to_client(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)

        data = {"event": "connected", "address": "AA:BB:CC", "battery": 80}
        await mgr.broadcast(data)

        ws.send_text.assert_called_once_with(json.dumps(data))

    async def test_broadcast_reaches_all_clients(self):
        mgr = ConnectionManager()
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        for ws in (ws1, ws2, ws3):
            await mgr.connect(ws)

        await mgr.broadcast({"event": "ping"})

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        ws3.send_text.assert_called_once()

    async def test_broadcast_removes_dead_client(self):
        """A client whose send_text raises must be silently removed."""
        mgr = ConnectionManager()
        ws = _make_ws()
        ws.send_text.side_effect = Exception("connection lost")
        await mgr.connect(ws)

        await mgr.broadcast({"event": "test"})

        assert mgr.client_count == 0

    async def test_broadcast_continues_after_dead_client(self):
        """A dead client must not prevent other clients from receiving messages."""
        mgr = ConnectionManager()
        dead_ws = _make_ws()
        dead_ws.send_text.side_effect = Exception("broken pipe")
        live_ws = _make_ws()

        await mgr.connect(dead_ws)
        await mgr.connect(live_ws)

        await mgr.broadcast({"event": "test"})

        live_ws.send_text.assert_called_once()
        assert mgr.client_count == 1  # only live_ws remains


# ---------------------------------------------------------------------------
# client_count
# ---------------------------------------------------------------------------


class TestClientCount:
    def test_initial_count_is_zero(self):
        mgr = ConnectionManager()
        assert mgr.client_count == 0
