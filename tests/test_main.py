"""Tests for coyote_server/main.py internals."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import coyote_server.main as main_mod


def _make_state(connected: bool = False) -> SimpleNamespace:
    device = SimpleNamespace(
        is_connected=connected,
        address="AA:BB" if connected else None,
        battery_level=77 if connected else 0,
        disconnect=AsyncMock(),
    )
    return SimpleNamespace(device=device)


@pytest.mark.asyncio
class TestHandleWsMessage:
    async def test_ignores_non_string_type(self):
        await main_mod._handle_ws_message({"type": 123})

    async def test_ignores_unsupported_string_type(self):
        await main_mod._handle_ws_message({"type": "unsupported"})


@pytest.mark.asyncio
class TestWebsocketEndpoint:
    async def test_sends_disconnected_event_on_connect(self):
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=[main_mod.WebSocketDisconnect()])

        with patch("coyote_server.state.app_state", state), patch.object(
            main_mod.ws_manager, "connect", new=AsyncMock()
        ), patch.object(main_mod.ws_manager, "disconnect") as disconnect_mock:
            await main_mod.websocket_endpoint(ws)

        ws.send_json.assert_awaited_once()
        disconnect_mock.assert_called_once_with(ws)

    async def test_dispatches_valid_dict_messages(self):
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(
            side_effect=[json.dumps({"type": "noop"}), main_mod.WebSocketDisconnect()]
        )

        with patch("coyote_server.state.app_state", state), patch.object(
            main_mod.ws_manager, "connect", new=AsyncMock()
        ), patch.object(main_mod.ws_manager, "disconnect"), patch.object(
            main_mod, "_handle_ws_message", new=AsyncMock()
        ) as handler_mock:
            await main_mod.websocket_endpoint(ws)

        handler_mock.assert_awaited_once()

    async def test_ignores_invalid_json(self):
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=["not-json", main_mod.WebSocketDisconnect()])

        with patch("coyote_server.state.app_state", state), patch.object(
            main_mod.ws_manager, "connect", new=AsyncMock()
        ), patch.object(main_mod.ws_manager, "disconnect"), patch.object(
            main_mod, "_handle_ws_message", new=AsyncMock()
        ) as handler_mock:
            await main_mod.websocket_endpoint(ws)

        handler_mock.assert_not_awaited()


@pytest.mark.asyncio
class TestLifespan:
    async def test_lifespan_disconnects_on_shutdown_when_connected(self):
        state = _make_state(True)
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass
        state.device.disconnect.assert_awaited_once()

    async def test_lifespan_ignores_disconnect_errors(self):
        state = _make_state(True)
        state.device.disconnect = AsyncMock(side_effect=RuntimeError("x"))
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass

    async def test_lifespan_no_disconnect_when_not_connected(self):
        state = _make_state(False)
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass
        state.device.disconnect.assert_not_awaited()


class TestRunEntrypoint:
    def test_run_invokes_uvicorn(self):
        with patch.object(main_mod.logging, "basicConfig") as basic_config, patch.object(
            main_mod.uvicorn, "run"
        ) as uvicorn_run:
            main_mod.run()

        basic_config.assert_called_once()
        uvicorn_run.assert_called_once_with(
            "coyote_server.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
        )
