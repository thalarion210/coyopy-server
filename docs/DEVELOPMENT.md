# Development

## Dependency model

coyote-server is intentionally split from coyopy.

- Runtime and test code import coyopy as an external dependency.
- There is no vendored copy of coyopy code in this repository.
- The dependency is currently resolved directly from GitHub because coyopy is not yet published on PyPI.

Current requirement:

```text
coyopy @ git+https://github.com/thalarion210/coyopy.git@main
```

If coyopy is published to PyPI later, replace the direct reference with a versioned package requirement.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

Run the app:

```bash
coyote-server
```

## Quality gates

```bash
python -m ruff check .
python -m mypy coyote_server
python -m pytest
python -m build
```

## GitHub Actions

The CI workflow runs on Python 3.11, 3.12 and 3.13 and executes:

1. dependency installation from requirements-dev.txt
2. Ruff
3. mypy on the published package
4. pytest with coverage
5. package build

## Release notes

Before creating a public release, verify these points:

1. coyopy main is compatible with the server release, or pin the dependency to a tag or commit.
2. The UI screenshot in docs/assets matches the current web UI.
3. coverage.xml, dist/, caches and temporary coverage files are not committed.
4. The changelog reflects any API or setup changes.
