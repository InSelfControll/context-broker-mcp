"""Bind-safety and shared-token auth helpers for network surfaces.

Loopback binds stay open (local editor integrations). Anything beyond
loopback must either present CONTEXT_BROKER_AUTH_TOKEN per request or be
explicitly allowed via CONTEXT_BROKER_ALLOW_UNAUTHENTICATED_BIND=1.
"""

import hmac
from collections.abc import Mapping

from context_broker.config import (
    ALLOW_UNAUTHENTICATED_BIND,
    AUTH_TOKEN,
    LOOPBACK_HOST,
)

_LOOPBACK_NAMES = {LOOPBACK_HOST, "localhost", "::1"}


def is_loopback_host(host: str) -> bool:
    """Return True when *host* only accepts local connections."""
    return host in _LOOPBACK_NAMES


def assert_bind_allowed(host: str, port: int, surface: str) -> None:
    """Refuse to bind *surface* beyond loopback without authentication."""
    if is_loopback_host(host) or ALLOW_UNAUTHENTICATED_BIND or AUTH_TOKEN:
        return
    raise SystemExit(
        f"{surface} refuses to bind {host}:{port} without authentication. "
        "Set CONTEXT_BROKER_AUTH_TOKEN (preferred) or, on a trusted network, "
        "CONTEXT_BROKER_ALLOW_UNAUTHENTICATED_BIND=1."
    )


def token_from(headers: Mapping, query_token: str = "") -> str:
    """Extract a bearer token from request headers or a query parameter."""
    get = getattr(headers, "get", None)
    auth = (get("authorization", "") if get else "") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return query_token


def token_valid(candidate: str) -> bool:
    """Constant-time check of *candidate* against CONTEXT_BROKER_AUTH_TOKEN.

    When no token is configured, every candidate passes — bind gating
    (assert_bind_allowed) is then the exposure guard.
    """
    if not AUTH_TOKEN:
        return True
    return hmac.compare_digest(candidate, AUTH_TOKEN)
