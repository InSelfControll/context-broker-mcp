"""Security-sensitive configuration default tests."""

from __future__ import annotations

import importlib
from typing import Any

import context_broker.config as config


def test_network_transport_defaults_to_loopback(monkeypatch: Any) -> None:
    monkeypatch.delenv("CONTEXT_BROKER_HOST", raising=False)

    reloaded = importlib.reload(config)

    assert reloaded.HOST == "127.0.0.1"
    assert reloaded.UCR_PUBLIC_SURFACE_ONLY is False
