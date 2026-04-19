"""Tests for coyote_server/main.py internals."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

import coyote_server.main as main_mod
from coyote_server.ws import ws_manager


def _make_state(connected: bool = False) -> SimpleNamespace:
    device = SimpleNamespace(
        is_connected=connected,
        address="AA:BB" if connected else None,
        battery_level=77 if connected else 0,
        disconnect=AsyncMock(),
    )
    manager = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        pause=MagicMock(),
    )
    return SimpleNamespace(device=device, manager=manager)


@pytest.mark.asyncio
class TestHandleWsMessage:
    async def test_ignores_non_string_type(self) -> None:
        await main_mod._handle_ws_message({"type": 123})

    async def test_ignores_unsupported_string_type(self) -> None:
        await main_mod._handle_ws_message({"type": "unsupported"})


@pytest.mark.asyncio
class TestWebsocketEndpoint:
    async def test_sends_disconnected_event_on_connect(self) -> None:
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=[WebSocketDisconnect()])

        with (
            patch("coyote_server.state.app_state", state),
            patch.object(ws_manager, "connect", new=AsyncMock()),
            patch.object(ws_manager, "disconnect") as disconnect_mock,
        ):
            await main_mod.websocket_endpoint(ws)

        ws.send_json.assert_awaited_once()
        disconnect_mock.assert_called_once_with(ws)

    async def test_dispatches_valid_dict_messages(self) -> None:
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=[json.dumps({"type": "noop"}), WebSocketDisconnect()])

        with (
            patch("coyote_server.state.app_state", state),
            patch.object(ws_manager, "connect", new=AsyncMock()),
            patch.object(ws_manager, "disconnect"),
            patch.object(main_mod, "_handle_ws_message", new=AsyncMock()) as handler_mock,
        ):
            await main_mod.websocket_endpoint(ws)

        handler_mock.assert_awaited_once()

    async def test_ignores_invalid_json(self) -> None:
        state = _make_state(False)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=["not-json", WebSocketDisconnect()])

        with (
            patch("coyote_server.state.app_state", state),
            patch.object(ws_manager, "connect", new=AsyncMock()),
            patch.object(ws_manager, "disconnect"),
            patch.object(main_mod, "_handle_ws_message", new=AsyncMock()) as handler_mock,
        ):
            await main_mod.websocket_endpoint(ws)

        handler_mock.assert_not_awaited()


@pytest.mark.asyncio
class TestLifespan:
    async def test_lifespan_disconnects_on_shutdown_when_connected(self) -> None:
        state = _make_state(True)
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass
        state.device.disconnect.assert_awaited_once()

    async def test_lifespan_ignores_disconnect_errors(self) -> None:
        state = _make_state(True)
        state.device.disconnect = AsyncMock(side_effect=RuntimeError("x"))
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass

    async def test_lifespan_no_disconnect_when_not_connected(self) -> None:
        state = _make_state(False)
        with patch("coyote_server.state.app_state", state):
            async with main_mod.lifespan(main_mod.app):
                pass
        state.device.disconnect.assert_not_awaited()

    async def test_lifespan_auto_connect_disabled_via_env(self) -> None:
        state = _make_state(False)
        with (
            patch("coyote_server.state.app_state", state),
            patch.dict("os.environ", {"COYOTE_AUTO_CONNECT": "false"}),
        ):
            async with main_mod.lifespan(main_mod.app):
                pass
        state.manager.start.assert_not_awaited()
        state.manager.pause.assert_called_once()


class TestRunEntrypoint:
    def test_run_invokes_uvicorn(self) -> None:
        with (
            patch("coyote_server.main.logging.basicConfig") as basic_config,
            patch.dict("os.environ", {}, clear=True),
            patch("coyote_server.main.uvicorn.run") as uvicorn_run,
        ):
            main_mod.run()

        basic_config.assert_called_once()
        uvicorn_run.assert_called_once_with(
            "coyote_server.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
        )

    def test_run_uses_environment_overrides(self) -> None:
        with (
            patch("coyote_server.main.logging.basicConfig"),
            patch.dict(
                "os.environ",
                {
                    "COYOTE_SERVER_HOST": "127.0.0.1",
                    "COYOTE_SERVER_PORT": "9000",
                    "COYOTE_SERVER_RELOAD": "true",
                },
                clear=True,
            ),
            patch("coyote_server.main.uvicorn.run") as uvicorn_run,
        ):
            main_mod.run()

        uvicorn_run.assert_called_once_with(
            "coyote_server.main:app",
            host="127.0.0.1",
            port=9000,
            reload=True,
        )


class TestWebAssets:
    def test_packaged_web_dir_exists(self) -> None:
        assert main_mod._WEB_DIR.is_dir()
