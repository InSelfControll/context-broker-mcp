"""
Resolve the user peer id ("who is asking the question?").

Priority (highest first):
  1. Explicit ``user_peer_id`` argument passed to the caller.
  2. ``CONTEXT_BROKER_ACCOUNT_NAME_OVERRIDE`` env var (any non-empty value).
  3. OS account name (``getpass.getuser()``) when ``CONTEXT_BROKER_USE_ACCOUNT_NAME``
     is enabled.
  4. ``HONCHO_USER_PEER_ID`` (default 'user').

The assistant peer id is never affected by this resolver.
"""

from __future__ import annotations

import getpass

from context_broker.config import (
    ACCOUNT_NAME_OVERRIDE,
    HONCHO_USER_PEER_ID,
    USE_ACCOUNT_NAME,
)


def _sanitize(value: str) -> str:
    """Reduce ``value`` to chars safe for peer ids: alnum, ``-``, ``_``, ``.``."""
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "-" for c in value).strip("-")


def _account_name() -> str:
    """Best-effort lookup of the OS account name."""
    try:
        return getpass.getuser()
    except Exception:
        return ""


def resolve_user_peer_id(explicit: str = "") -> str:
    """Return the user peer id to use for a save/load call."""
    if explicit and explicit.strip():
        return explicit.strip()
    if ACCOUNT_NAME_OVERRIDE:
        cleaned = _sanitize(ACCOUNT_NAME_OVERRIDE)
        if cleaned:
            return cleaned
    if USE_ACCOUNT_NAME:
        account = _sanitize(_account_name())
        if account:
            return account
    return HONCHO_USER_PEER_ID


def describe_user_identity() -> dict[str, str | bool]:
    """Diagnostic dict for surfacing the resolved identity in status tools."""
    return {
        "use_account_name": USE_ACCOUNT_NAME,
        "account_name_override": ACCOUNT_NAME_OVERRIDE or "",
        "detected_account_name": _account_name(),
        "resolved_user_peer_id": resolve_user_peer_id(),
        "default_user_peer_id": HONCHO_USER_PEER_ID,
    }
