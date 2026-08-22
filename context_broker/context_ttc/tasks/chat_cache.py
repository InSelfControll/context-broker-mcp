"""
Redis-backed chat-payload cache.

Caches the full `load_chat_context` response under a TTL so repeated loads of
the same (project, session) pair are served from Redis instead of being
re-fetched from Honcho or re-assembled from the Redis message log.

Active whenever CONTEXT_BROKER_REDIS_URL is set and CHAT_CACHE_TTL_SECONDS > 0,
regardless of which cross-chat context backend (`honcho` or `redis`) is selected.
"""

import hashlib
import json
import os
import time
from typing import Any

from context_broker.config import (
    CHAT_CACHE_TTL_SECONDS,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)
from context_broker.context_ttc.tools.id_tools import safe_id

_REDIS_CLIENT: Any = None
_REDIS_RETRY_AFTER: float = 0.0
_REDIS_RETRY_BACKOFF_SECONDS = 30.0
"""How long to wait before retrying Redis after a connection failure."""


def reset_client_for_tests(client: Any | None = None, *, unavailable: bool = False) -> None:
    """Test hook: inject a fake Redis client or reset state."""
    global _REDIS_CLIENT, _REDIS_RETRY_AFTER
    _REDIS_CLIENT = client
    _REDIS_RETRY_AFTER = float("inf") if unavailable else 0.0


def _enabled() -> bool:
    return bool(REDIS_URL) and CHAT_CACHE_TTL_SECONDS > 0


def _get_client() -> Any:
    """Return a Redis client used solely for the chat cache.

    A connection failure trips a short circuit breaker: the cache backs off
    for _REDIS_RETRY_BACKOFF_SECONDS and then retries, instead of latching
    off until process restart.
    """
    global _REDIS_CLIENT, _REDIS_RETRY_AFTER
    if not _enabled() or time.monotonic() < _REDIS_RETRY_AFTER:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis

        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        _REDIS_CLIENT = client
        _REDIS_RETRY_AFTER = 0.0
        return _REDIS_CLIENT
    except Exception:
        _REDIS_RETRY_AFTER = time.monotonic() + _REDIS_RETRY_BACKOFF_SECONDS
        return None


def _project_digest(project_root: str) -> str:
    root = os.path.abspath(project_root or os.getcwd())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _safe_id(session_id: str) -> str:
    return safe_id(session_id, "default")


def _signature(**kwargs: Any) -> str:
    """Stable digest of the parameters that affect a load response."""
    payload = json.dumps(kwargs, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _key(project_root: str, session_id: str, signature: str) -> str:
    digest = _project_digest(project_root)
    return ":".join(
        (REDIS_KEY_PREFIX, "chat-cache", digest, _safe_id(session_id), signature)
    )


def _index_key(project_root: str, session_id: str) -> str:
    digest = _project_digest(project_root)
    return ":".join((REDIS_KEY_PREFIX, "chat-cache-idx", digest, _safe_id(session_id)))


def get(project_root: str, session_id: str, **params: Any) -> dict[str, Any] | None:
    """Return a cached chat payload, or None on miss / cache disabled."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_key(project_root, session_id, _signature(**params)))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def put(
    project_root: str,
    session_id: str,
    payload: dict[str, Any],
    **params: Any,
) -> bool:
    """Cache a chat payload for the configured TTL. Returns True on success."""
    client = _get_client()
    if client is None:
        return False
    signature = _signature(**params)
    key = _key(project_root, session_id, signature)
    try:
        # Payload + per-session invalidation index commit in one MULTI/EXEC so
        # a partial failure can never orphan a payload the invalidator cannot
        # discover. SET carries EX inline so no key persists without a TTL.
        idx = _index_key(project_root, session_id)
        pipe = client.pipeline(transaction=True)
        pipe.set(
            key,
            json.dumps(payload, ensure_ascii=False, default=str),
            ex=CHAT_CACHE_TTL_SECONDS,
        )
        pipe.sadd(idx, signature)
        pipe.expire(idx, CHAT_CACHE_TTL_SECONDS)
        pipe.execute()
        return True
    except Exception:
        return False


def invalidate(project_root: str, session_id: str) -> int:
    """Drop every cached payload for (project, session). Returns count removed."""
    client = _get_client()
    if client is None:
        return 0
    idx = _index_key(project_root, session_id)
    try:
        signatures = client.smembers(idx) or set()
    except Exception:
        return 0
    if not signatures:
        try:
            client.delete(idx)
        except Exception:
            pass
        return 0
    pipe = client.pipeline(transaction=True)
    for signature in signatures:
        pipe.delete(_key(project_root, session_id, signature))
    pipe.delete(idx)
    try:
        results = pipe.execute()
    except Exception:
        return 0
    return sum(1 for r in (results or [])[:-1] if r)


def status() -> dict[str, Any]:
    """Diagnostic status for the chat cache."""
    info: dict[str, Any] = {
        "enabled": _enabled(),
        "ttl_seconds": CHAT_CACHE_TTL_SECONDS,
        "redis_url_set": bool(REDIS_URL),
    }
    if not _enabled():
        info["available"] = False
        info["message"] = "Chat cache requires CONTEXT_BROKER_REDIS_URL and a non-zero TTL."
        return info
    client = _get_client()
    info["available"] = client is not None
    info["message"] = "Chat cache connected." if client else "Redis unavailable; cache disabled."
    return info
