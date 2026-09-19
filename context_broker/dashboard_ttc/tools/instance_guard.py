"""Detect an already-running Context Broker dashboard instance."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from context_broker.config import LOOPBACK_HOST, UNSPECIFIED_HOSTS


def dashboard_already_running(host: str, port: int) -> bool:
    """Return whether the configured address serves this dashboard's status API."""
    probe_host = LOOPBACK_HOST if host in UNSPECIFIED_HOSTS else host
    status_url = f"http://{probe_host}:{port}/api/status"
    try:
        with urllib.request.urlopen(status_url, timeout=1.0) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read())
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and "backend" in payload
