"""Environment isolation helpers for downstream stdio processes."""

from __future__ import annotations

import os

_SAFE_ENV_KEYS = {
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "TMPDIR",
    "XDG_CACHE_HOME", "XDG_CONFIG_DIRS", "XDG_CONFIG_HOME", "XDG_DATA_DIRS",
    "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "XDG_STATE_HOME",
}


def filtered_stdio_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an allowlisted environment plus explicitly configured values."""
    env = {
        key: value
        for key in _SAFE_ENV_KEYS
        if (value := os.getenv(key)) is not None
    }
    env.update(extra_env or {})
    return env
