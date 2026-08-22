"""
Redis-backed cross-chat context tasks.

Mirrors the Honcho context API so Redis can serve as a Honcho-equivalent store
for cross-session context sharing. Schema:

  <prefix>:ctx:projects                       SET of project digests
  <prefix>:ctx:project:<digest>               HASH {name, root}
  <prefix>:ctx:project:<digest>:sessions      SET of session ids
  <prefix>:ctx:project:<digest>:session:<id>  LIST of JSON message payloads
"""

import hashlib
import json
import os
import time
from typing import Any

from context_broker.config import (
    CONTEXT_BACKEND,
    HONCHO_ASSISTANT_PEER_ID,
    HONCHO_SESSION_PREFIX,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)
from context_broker.context_ttc.tasks import chat_ledger
from context_broker.context_ttc.tools.id_tools import safe_id
from context_broker.identity import resolve_user_peer_id
from context_broker.project import get_project_name

_REDIS_CLIENT: Any = None


def _redis_enabled() -> bool:
    """Return whether Redis is the selected cross-chat context backend."""
    return CONTEXT_BACKEND == "redis"


def _get_redis_client() -> Any:
    """Create a Redis client lazily."""
    global _REDIS_CLIENT
    if not _redis_enabled():
        raise RuntimeError("Redis context backend is disabled")
    if not REDIS_URL:
        raise RuntimeError(
            "Redis context backend requires CONTEXT_BROKER_REDIS_URL"
        )
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis
    except Exception as e:
        raise RuntimeError("Redis context backend requires the 'redis' package") from e
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    _REDIS_CLIENT = client
    return _REDIS_CLIENT


def reset_client_for_tests(client: Any | None = None) -> None:
    """Test hook: inject or reset the Redis client."""
    global _REDIS_CLIENT
    _REDIS_CLIENT = client


def _safe_id(value: str, default: str) -> str:
    """Normalize identifiers before keying Redis."""
    return safe_id(value, default)


def project_digest(project_root: str) -> str:
    """Return a stable digest used to scope Redis keys per project."""
    root = os.path.abspath(project_root or os.getcwd())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _k(*parts: str) -> str:
    """Compose a Redis key with the configured prefix."""
    return ":".join((REDIS_KEY_PREFIX, "ctx", *parts))


def _session_key(digest: str, session_id: str) -> str:
    safe = _safe_id(session_id, "default")
    return _k("project", digest, "session", safe)


def _record_project(client: Any, digest: str, project_root: str) -> None:
    name = get_project_name(project_root) if project_root else "unknown"
    client.sadd(_k("projects"), digest)
    client.hset(_k("project", digest), mapping={"name": name, "root": project_root or ""})


def _user_key(digest: str, peer_id: str) -> str:
    return _k("project", digest, "user", peer_id)


def _user_requests_key(digest: str, peer_id: str) -> str:
    return _k("project", digest, "user", peer_id, "requests")


def _record_user_activity(
    client: Any,
    digest: str,
    peer_id: str,
    session_id: str,
    timestamp: float,
) -> None:
    """Track a per-user activity tick in one transaction.

    first_seen is set only on the user's first request; last_seen is bumped
    and request_count is incremented atomically (HINCRBY) so concurrent
    requests can never lose a tick. The audit-log append rides in the same
    MULTI/EXEC so it cannot drift from the counter.
    """
    if not peer_id:
        return
    user_key = _user_key(digest, peer_id)
    existing = client.hgetall(user_key) or {}
    mapping: dict[str, str] = {"last_seen": repr(timestamp)}
    if "first_seen" not in existing:
        mapping["first_seen"] = repr(timestamp)
    pipe = client.pipeline(transaction=True)
    pipe.sadd(_k("project", digest, "users"), peer_id)
    pipe.hset(user_key, mapping=mapping)
    pipe.hincrby(user_key, "request_count", 1)
    pipe.rpush(
        _user_requests_key(digest, peer_id),
        json.dumps(
            {"timestamp": timestamp, "session_id": session_id},
            ensure_ascii=False,
        ),
    )
    pipe.execute()


def get_context_backend_status() -> dict[str, Any]:
    """Return user-visible status for the Redis context backend."""
    status: dict[str, Any] = {
        "backend": CONTEXT_BACKEND,
        "enabled": _redis_enabled(),
        "redis_url_set": bool(REDIS_URL),
        "key_prefix": REDIS_KEY_PREFIX,
    }
    if not _redis_enabled():
        status["available"] = False
        status["message"] = "Set CONTEXT_BROKER_CONTEXT_BACKEND=redis to enable Redis context."
        return status
    try:
        _get_redis_client()
        status["available"] = True
        status["message"] = "Redis context backend connected."
    except Exception as e:
        status["available"] = False
        status["message"] = str(e)
    return status


def save_redis_chat_context(
    session_id: str,
    project_root: str = "",
    user_message: str = "",
    assistant_message: str = "",
    user_peer_id: str = "",
    assistant_peer_id: str = "",
) -> dict[str, Any]:
    """Persist chat turns to Redis."""
    client = _get_redis_client()
    digest = project_digest(project_root)
    _record_project(client, digest, project_root)

    safe_session = _safe_id(session_id, "default")
    full_session = f"{HONCHO_SESSION_PREFIX}-{safe_session}"

    user_id = _safe_id(resolve_user_peer_id(user_peer_id), "user")
    assistant_id = _safe_id(assistant_peer_id, HONCHO_ASSISTANT_PEER_ID)

    messages: list[dict[str, Any]] = []
    now = time.time()
    if user_message:
        messages.append({"peer_id": user_id, "content": user_message, "created_at": now})
    if assistant_message:
        messages.append({"peer_id": assistant_id, "content": assistant_message, "created_at": now})
    if not messages:
        raise ValueError("At least one of user_message or assistant_message is required")

    # Register the session and append its messages in one MULTI/EXEC so a
    # failure cannot leave a partially committed session behind.
    key = _session_key(digest, safe_session)
    pipe = client.pipeline(transaction=True)
    pipe.sadd(_k("project", digest, "sessions"), safe_session)
    for msg in messages:
        pipe.rpush(key, json.dumps(msg, ensure_ascii=False))
    pipe.execute()

    # Per-user activity audit: when each peer asked / answered.
    if user_message:
        _record_user_activity(client, digest, user_id, safe_session, now)
    if assistant_message:
        _record_user_activity(client, digest, assistant_id, safe_session, now)

    ledger_files = chat_ledger.append_turn(project_root, safe_session, messages)

    return {
        "backend": "redis",
        "session_id": full_session,
        "project_digest": digest,
        "messages_saved": len(messages),
        "user_peer_id": user_id,
        "assistant_peer_id": assistant_id,
        "ledger_files": ledger_files,
        "request_timestamp": now,
    }


def load_redis_chat_context(
    session_id: str,
    project_root: str = "",
    tokens: int = 0,
    summary: bool = True,
    search_query: str = "",
    limit_to_session: bool = True,
    user_peer_id: str = "",
    assistant_peer_id: str = "",
) -> dict[str, Any]:
    """Load Redis-backed session context. Signature matches the Honcho loader."""
    del tokens, summary, user_peer_id, assistant_peer_id, limit_to_session  # accepted for parity
    client = _get_redis_client()
    digest = project_digest(project_root)
    safe_session = _safe_id(session_id, "default")
    key = _session_key(digest, safe_session)
    raw = client.lrange(key, 0, -1) or []
    messages = [json.loads(item) for item in raw]
    if search_query:
        needle = search_query.lower()
        messages = [m for m in messages if needle in (m.get("content") or "").lower()]
    return {
        "backend": "redis",
        "session_id": f"{HONCHO_SESSION_PREFIX}-{safe_session}",
        "project_digest": digest,
        "messages": messages,
        "message_count": len(messages),
    }


def list_projects() -> list[dict[str, Any]]:
    """List every project with Redis-stored context (used by the dashboard)."""
    client = _get_redis_client()
    digests = sorted(client.smembers(_k("projects")) or [])
    out: list[dict[str, Any]] = []
    for digest in digests:
        meta = client.hgetall(_k("project", digest)) or {}
        session_count = client.scard(_k("project", digest, "sessions")) or 0
        out.append(
            {
                "digest": digest,
                "name": meta.get("name", "unknown"),
                "root": meta.get("root", ""),
                "session_count": int(session_count),
            }
        )
    return out


def _last_message_timestamp(client: Any, key: str) -> float:
    """Best-effort: return the `created_at` of the most recently appended message
    in a session LIST. Returns 0.0 when the list is empty or the tail entry has
    no timestamp."""
    try:
        tail = client.lindex(key, -1)
    except Exception:
        return 0.0
    if not tail:
        return 0.0
    try:
        return _coerce_float(json.loads(tail).get("created_at"))
    except Exception:
        return 0.0


def list_sessions(digest: str) -> list[dict[str, Any]]:
    """List sessions for a given project digest, most-recently-updated first."""
    client = _get_redis_client()
    ids = client.smembers(_k("project", digest, "sessions")) or []
    out: list[dict[str, Any]] = []
    for session_id in ids:
        key = _session_key(digest, session_id)
        message_count = client.llen(key) or 0
        out.append(
            {
                "session_id": session_id,
                "full_session_id": f"{HONCHO_SESSION_PREFIX}-{session_id}",
                "message_count": int(message_count),
                "last_message_at": _last_message_timestamp(client, key),
            }
        )
    out.sort(key=lambda s: (s["last_message_at"], s["session_id"]), reverse=True)
    return out


def load_session(digest: str, session_id: str) -> dict[str, Any]:
    """Load every message stored for one (project, session) pair."""
    client = _get_redis_client()
    raw = client.lrange(_session_key(digest, session_id), 0, -1) or []
    messages = [json.loads(item) for item in raw]
    meta = client.hgetall(_k("project", digest)) or {}
    return {
        "project": {"digest": digest, **meta},
        "session_id": session_id,
        "full_session_id": f"{HONCHO_SESSION_PREFIX}-{session_id}",
        "messages": messages,
        "message_count": len(messages),
    }


def _coerce_float(value: Any) -> float:
    """Parse a stored timestamp field back to a float (0 on failure)."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def list_users(digest: str) -> list[dict[str, Any]]:
    """Return per-user activity summaries for one project, most-recently-active first."""
    client = _get_redis_client()
    peer_ids = client.smembers(_k("project", digest, "users")) or []
    out: list[dict[str, Any]] = []
    for peer_id in peer_ids:
        meta = client.hgetall(_user_key(digest, peer_id)) or {}
        request_log_len = client.llen(_user_requests_key(digest, peer_id)) or 0
        try:
            request_count = int(meta.get("request_count", "0") or "0")
        except ValueError:
            request_count = 0
        out.append(
            {
                "peer_id": peer_id,
                "first_seen": _coerce_float(meta.get("first_seen")),
                "last_seen": _coerce_float(meta.get("last_seen")),
                "request_count": request_count,
                "request_log_length": int(request_log_len),
            }
        )
    out.sort(key=lambda u: (u["last_seen"], u["peer_id"]), reverse=True)
    return out


def load_user_activity(
    digest: str, peer_id: str, limit: int = 100
) -> dict[str, Any]:
    """Full per-user audit trail: HASH summary + N most recent requests."""
    client = _get_redis_client()
    meta = client.hgetall(_user_key(digest, peer_id)) or {}
    log_len = client.llen(_user_requests_key(digest, peer_id)) or 0
    start = max(0, int(log_len) - max(0, int(limit)))
    raw = client.lrange(_user_requests_key(digest, peer_id), start, -1) or []
    requests: list[dict[str, Any]] = []
    for item in raw:
        try:
            requests.append(json.loads(item))
        except Exception:
            continue
    try:
        request_count = int(meta.get("request_count", "0") or "0")
    except ValueError:
        request_count = 0
    return {
        "peer_id": peer_id,
        "project_digest": digest,
        "first_seen": _coerce_float(meta.get("first_seen")),
        "last_seen": _coerce_float(meta.get("last_seen")),
        "request_count": request_count,
        "requests": requests,
        "request_log_length": int(log_len),
        "limit": int(limit),
    }


def load_cross_session_matches(
    project_root: str,
    search_query: str,
    top_k: int = 10,
    per_session_limit: int = 50,
) -> dict[str, Any]:
    """Search every session of a project and return the most recent matching turns.

    "Important" is approximated as: substring match on ``search_query`` (case-
    insensitive), ranked by message ``created_at`` descending. This is a
    deliberately simple ranker — it gives you the user's "only important data
    cross chats / sessions" view without pulling in a vector model.
    """
    client = _get_redis_client()
    digest = project_digest(project_root)
    needle = (search_query or "").strip().lower()
    session_ids = sorted(client.smembers(_k("project", digest, "sessions")) or [])

    matches: list[dict[str, Any]] = []
    for session_id in session_ids:
        raw = client.lrange(_session_key(digest, session_id), 0, -1) or []
        if per_session_limit and len(raw) > per_session_limit:
            raw = raw[-per_session_limit:]
        for item in raw:
            try:
                msg = json.loads(item)
            except Exception:
                continue
            content = str(msg.get("content", ""))
            if needle and needle not in content.lower():
                continue
            matches.append({**msg, "session_id": session_id})

    matches.sort(key=lambda m: float(m.get("created_at", 0) or 0), reverse=True)
    capped = matches[: max(0, int(top_k))]
    return {
        "project_digest": digest,
        "search_query": search_query,
        "sessions_scanned": len(session_ids),
        "match_count": len(capped),
        "total_matches": len(matches),
        "matches": capped,
    }
