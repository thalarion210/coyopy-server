# coyote-server

[![CI](https://github.com/thalarion210/coyopy-server/actions/workflows/ci.yml/badge.svg)](https://github.com/thalarion210/coyopy-server/actions/workflows/ci.yml)

Standalone FastAPI server and lightweight browser UI for the DG-Labs Coyote.

## Scope

This repository contains:

- a REST API for scan, connect, disconnect and channel control
- an outbound-only WebSocket stream for live device events
- a small no-build browser UI for administration and testing

This repository does not contain game logic. Game-oriented flows belong in separate applications that consume coyopy directly or talk to this server over HTTP and WebSocket.

## Dependency model

coyote-server is intentionally decoupled from coyopy source code.

- It depends on coyopy as an external package requirement.
- It does not vendor or copy coyopy modules.
- CI installs coyopy from GitHub, not from a sibling checkout.

At the moment coyopy is referenced directly from GitHub because it is not yet available on PyPI:

```text
coyopy @ git+https://github.com/thalarion210/coyopy.git@main
```

Once coyopy is published to PyPI, this should be replaced with a normal versioned dependency.

## Screenshot

![Browser UI overview](docs/assets/control-ui.png)

## Installation

### End users

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
```

### Developers

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Run

```bash
coyote-server
```

Then open:

- http://127.0.0.1:8000 for the browser UI
- http://127.0.0.1:8000/docs for the OpenAPI UI

## API summary

### Device endpoints

- POST /api/scan
- POST /api/connect
- POST /api/disconnect
- GET /api/status

### Channel endpoints

- GET /api/channel/{a|b}
- PUT /api/channel/{a|b}/power
- PUT /api/channel/{a|b}/mode
- PUT /api/channel/{a|b}/pattern

### WebSocket

- GET /ws
- outbound events: connected, disconnected, battery, power, mode, frame, error

See docs/API.md for request and response details.

## Development checks

```bash
python -m ruff check .
python -m mypy coyote_server
python -m pytest
python -m build
```

Current validated state in this workspace:

- 99 tests passing
- 98% coverage
- mypy clean on coyote_server
- package build succeeds

## Repository layout

- coyote_server/ contains the packaged FastAPI application
- tests/ contains API, model, state, websocket and entrypoint tests
- web/ contains the static browser UI
- docs/ contains API and development notes

## GitHub readiness

The repository is prepared for GitHub with:

- a multi-version CI workflow
- ignore rules for caches, coverage outputs and build artifacts
- package metadata for wheel and sdist builds
- standalone documentation that does not rely on a monorepo sibling checkout

## Notes

- The browser UI is intentionally simple and aimed at device administration, not game logic.
- For reproducible releases you should pin the coyopy dependency to a tag or commit instead of main.
