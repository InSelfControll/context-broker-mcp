"""
.env loader for Context Broker.

Walks up from a starting directory looking for a `.env` file and loads its
values into ``os.environ`` *without* overriding variables already set by the
parent process (so editor-injected MCP env still wins).

Uses a small local parser so startup behavior cannot change based on an
undeclared package present in the host environment.
"""

import os
from pathlib import Path

from context_broker.utils import log

_DEFAULT_FILENAMES = (".env", ".env.local")


def auto_load_env_enabled() -> bool:
    """Return whether startup may discover and load a local environment file."""
    return os.getenv("CONTEXT_BROKER_AUTO_LOAD_ENV", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def find_env_file(start: str | Path | None = None, *, filenames: tuple[str, ...] = _DEFAULT_FILENAMES) -> Path | None:
    """Return the nearest .env file walking upward from ``start`` (default: CWD)."""
    here = Path(start or os.getcwd()).resolve()
    for directory in (here, *here.parents):
        for name in filenames:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _parse_simple(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE per line, # comments, quoted values stripped."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _load_values(path: Path) -> dict[str, str]:
    return _parse_simple(path)


def load_env(
    start: str | Path | None = None,
    *,
    override: bool = False,
    quiet: bool = False,
) -> dict[str, str]:
    """Load the nearest .env into os.environ.

    Returns the dict of values actually written (i.e. excluding keys that were
    already set in the parent environment when ``override`` is False).
    """
    path = find_env_file(start)
    if path is None:
        return {}

    values = _load_values(path)
    applied: dict[str, str] = {}
    for key, value in values.items():
        if not override and key in os.environ:
            continue
        os.environ.update({key: value})
        applied[key] = value

    if not quiet and applied:
        log(f"Loaded {len(applied)} env var(s) from {path}")
    return applied
