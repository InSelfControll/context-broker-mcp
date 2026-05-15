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
from typing import Any

from context_broker.config import (
    CHAT_CACHE_TTL_SECONDS,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)

_REDIS_CLIENT: Any = None
_REDIS_UNAVAILABLE = False


def reset_client_for_tests(client: Any | None = None, *, unavailable: bool = False) -> None:
    """Test hook: inject a fake Redis client or reset state."""
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE
    _REDIS_CLIENT = client
    _REDIS_UNAVAILABLE = unavailable


def _enabled() -> bool:
    return bool(REDIS_URL) and CHAT_CACHE_TTL_SECONDS > 0


def _get_client() -> Any:
    """Return a Redis client used solely for the chat cache."""
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE
    if not _enabled() or _REDIS_UNAVAILABLE:
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
        return _REDIS_CLIENT
    except Exception:
        _REDIS_UNAVAILABLE = True
        return None


def _project_digest(project_root: str) -> str:
    root = os.path.abspath(project_root or os.getcwd())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _safe_id(session_id: str) -> str:
    candidate = (session_id or "default").strip() or "default"
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "-" for c in candidate)


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
        # SET with EX in one round-trip so the key can never persist without a
        # TTL (avoids the SET/EXPIRE race that left stale payloads on partial
        # failure).
        client.set(
            key,
            json.dumps(payload, ensure_ascii=False, default=str),
            ex=CHAT_CACHE_TTL_SECONDS,
        )
        # Maintain a per-session index so invalidation can wipe every signature.
        idx = _index_key(project_root, session_id)
        client.sadd(idx, signature)
        client.expire(idx, CHAT_CACHE_TTL_SECONDS)
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
    removed = 0
    for signature in signatures:
        try:
            client.delete(_key(project_root, session_id, signature))
            removed += 1
        except Exception:
            continue
    try:
        client.delete(idx)
    except Exception:
        pass
    return removed


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
