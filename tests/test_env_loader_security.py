"""Security regressions for local environment loading."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

from context_broker import env_loader
from context_broker.env_loader import load_env


def test_env_loader_ignores_undeclared_dotenv_module(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SAFE_VALUE=expected\n", encoding="utf-8")
    fake_dotenv = SimpleNamespace(dotenv_values=lambda _path: {"INJECTED": "yes"})
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setenv("SAFE_VALUE", "original")
    monkeypatch.setenv("INJECTED", "original")

    applied = load_env(tmp_path, override=True, quiet=True)

    assert applied == {"SAFE_VALUE": "expected"}


def test_auto_load_env_enabled_respects_disable_flag(monkeypatch: Any) -> None:
    monkeypatch.setenv("CONTEXT_BROKER_AUTO_LOAD_ENV", "0")
    enabled = getattr(env_loader, "auto_load_env_enabled", None)

    assert enabled is not None
    assert enabled() is False
