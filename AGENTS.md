# Agent Guidelines for server-monitor-codex

## Project Overview

This is a Python FastAPI dashboard application for monitoring two GPU cloud servers via SSH.
Source code lives in `src/server_monitor/`, tests in `tests/`.

## Build / Lint / Test Commands

### Package Management (uv)
```bash
# Install all dependencies (including dev)
uv sync --all-groups

# Add a new dependency
uv add <package>

# Add a new dev dependency
uv add --group dev <package>
```

### Linting (Ruff)
```bash
# Run ruff linter on entire project
uv run ruff check .

# Auto-fix issues where possible
uv run ruff check . --fix
```

### Testing (Pytest)
```bash
# Run all tests (quiet mode)
uv run pytest -q

# Run all tests with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_cli.py

# Run a single test by name
uv run pytest tests/test_cli.py::test_cli_main_uses_expected_defaults

# Run tests matching a pattern
uv run pytest -k "test_name_pattern"

# Run tests in a specific directory
uv run pytest tests/dashboard/

# Run with coverage
uv run pytest --cov=src/server_monitor

# Run the e2e tests (requires full system)
uv run pytest tests/e2e/
```

### Running the Application
```bash
# Run the dashboard server
uv run server-monitor-dashboard

# Run with custom host/port
uv run server-monitor-dashboard --host 0.0.0.0 --port 9090

# Run with auto-reload (local development)
uv run server-monitor-dashboard --reload
```

## Code Style Guidelines

### General
- Python 3.12+ required
- Always use `from __future__ import annotations` at the top of every file
- No comments in code unless explicitly requested
- Keep functions focused and reasonably small

### Type Annotations
- Use lowercase built-in types: `dict`, `list`, `str`, `float`, `int`, `bool`, `None`
- Use `X | None` syntax for optional types (not `Optional[X]`)
- Use `Literal[...]` for enumerated string values
- Use type aliases for complex types (e.g., `PanelName = Literal["system", "gpu", "git", "clash"]`)
- All public function signatures should have type hints

### Imports
Order imports as follows, separated by blank lines:
1. `from __future__ import annotations`
2. Standard library imports
3. Third-party imports (fastapi, pydantic, pytest, etc.)
4. Local application imports (from `server_monitor...`)

Example:
```python
from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from server_monitor.dashboard.settings import DashboardSettings
```

### Naming Conventions
- Classes: `PascalCase` (e.g., `DashboardRuntime`, `ServerSettings`)
- Functions/methods: `snake_case` (e.g., `build_dashboard_app`, `run_git_operation`)
- Private functions (internal use): prefix with `_` (e.g., `_build_parser`, `_find_server`)
- Variables: `snake_case` (e.g., `server_id`, `enabled_panels`)
- Type aliases: `PascalCase` (e.g., `PanelName`)
- Dataclass fields: `snake_case`
- Constants: `UPPER_SNAKE_CASE` (e.g., `STATUS_POLL_INLINE_BUDGET_SECONDS`)

### Dataclasses
- Use `@dataclass(slots=True)` for data models
- Use `field(default_factory=...)` for mutable default values
- Prefer dataclasses over dictionaries for structured data

Example:
```python
@dataclass(slots=True)
class ServerSettings:
    server_id: str
    ssh_alias: str
    working_dirs: list[str] = field(default_factory=list)
    enabled_panels: list[PanelName] = field(default_factory=lambda: ["system", "gpu", "git", "clash"])
```

### Datetime
- Use `datetime.UTC` (not `datetime.timezone.utc`) for timezone-aware UTC times
- Pattern: `datetime.now(UTC)` or `datetime.fromisoformat(...).astimezone(UTC)`

### Error Handling
- Always chain exceptions with `from exc` (e.g., `raise HTTPException(...) from exc`)
- Use specific exception types (e.g., `ValueError`, `KeyError`, `HTTPException`)
- For expected cancellation/suppression cases, use `contextlib.suppress`:
```python
with suppress(asyncio.CancelledError):
    await self._task
```
- Never silently swallow exceptions without logging or explicit intent

### FastAPI Routes (api.py)
- Use Pydantic `BaseModel` for request/response payloads
- Use `status.HTTP_*` constants for HTTP status codes
- Keep route handlers thin; delegate logic to service functions
- Use `asynccontextmanager` for lifespan management

### Async Code
- Use `asyncio.create_task()` for background tasks with named tasks when useful
- Always properly await or cancel background tasks on shutdown
- Use `asyncio.Event` for stop signals

### Testing
- Use `pytest` with `monkeypatch` for mocking
- Use `pytest-asyncio` for async tests (mark async tests with `@pytest.mark.asyncio`)
- Test file naming: `test_<module_name>.py`
- Test function naming: `test_<functionality_described>`
- Use `fixtures/` directory for test data files
- Group related tests in classes when appropriate

Example test:
```python
def test_cli_main_uses_expected_defaults(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(app_target: str, **kwargs):
        captured["app_target"] = app_target
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["server-monitor-dashboard"])

    cli.main()

    assert captured["app_target"] == "server_monitor.dashboard.main:build_dashboard_app"
    assert captured["kwargs"] == {"factory": True, "host": "127.0.0.1", "port": 8080, "reload": False}
```

### File Structure
```
src/server_monitor/
├── __init__.py
├── agent/           # Agent-related code
├── dashboard/      # Main dashboard application
│   ├── api.py      # FastAPI routes
│   ├── cli.py      # CLI entrypoint
│   ├── main.py     # App factory and runtime
│   ├── runtime.py  # Background polling runtime
│   ├── settings.py # Settings models and store
│   ├── parsers/    # Output parsers for SSH commands
│   └── ...
└── shared/         # Shared utilities

tests/
├── agent/
├── dashboard/      # Dashboard unit tests
│   └── parsers/    # Parser unit tests
├── e2e/            # End-to-end tests
├── fixtures/       # Test data files
└── shared/
```

### Docstrings
- Module docstrings: short one-line description at top of file
- Public function docstrings: describe purpose and params using:
```python
def build_dashboard_app():
    """Create dashboard app instance."""
```

### Pydantic Models
- Use for all API request/response payloads
- Inherit from `BaseModel`
- Use field defaults for optional values
