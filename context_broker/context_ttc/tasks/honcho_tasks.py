"""
Optional Honcho-backed cross-chat context tasks.
"""

import hashlib
import json
import os
from typing import Any

from context_broker.config import (
    CONTEXT_BACKEND,
    HONCHO_ASSISTANT_PEER_ID,
    HONCHO_CONTEXT_TOKENS,
    HONCHO_LIMIT_TO_SESSION,
    HONCHO_SESSION_PREFIX,
    HONCHO_USER_PEER_ID,
    HONCHO_WORKSPACE_ID,
)
from context_broker.context_ttc.tasks import chat_ledger
from context_broker.context_ttc.tools.identity_tools import normalize_identifier as _safe_id
from context_broker.identity import resolve_user_peer_id
from context_broker.project import get_project_name

_HONCHO_CLIENT: Any = None


def _honcho_enabled() -> bool:
    """Return whether Honcho is the selected cross-chat context backend."""
    return CONTEXT_BACKEND == "honcho"


def _get_honcho_client() -> Any:
    """Create a Honcho client lazily so the dependency stays optional."""
    global _HONCHO_CLIENT

    if not _honcho_enabled():
        raise RuntimeError("Honcho context backend is disabled")
    if _HONCHO_CLIENT is not None:
        return _HONCHO_CLIENT

    try:
        from honcho import Honcho
    except Exception as e:
        raise RuntimeError("Honcho context backend requires the 'honcho-ai' package") from e

    try:
        _HONCHO_CLIENT = Honcho(workspace_id=HONCHO_WORKSPACE_ID)
    except TypeError:
        _HONCHO_CLIENT = Honcho()
    return _HONCHO_CLIENT


def _honcho_session_id(session_id: str, project_root: str = "") -> str:
    """Scope Honcho sessions by project when a project root is available."""
    safe_session = _safe_id(session_id, "default")
    if not project_root:
        return f"{HONCHO_SESSION_PREFIX}-{safe_session}"

    root = os.path.abspath(project_root)
    project_name = _safe_id(get_project_name(root), "project")
    project_digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:10]
    return f"{HONCHO_SESSION_PREFIX}-{project_name}-{project_digest}-{safe_session}"


def get_context_backend_status() -> dict[str, Any]:
    """Return user-visible status for the cross-chat context backend."""
    status = {
        "backend": CONTEXT_BACKEND,
        "enabled": _honcho_enabled(),
        "workspace_id": HONCHO_WORKSPACE_ID,
        "session_prefix": HONCHO_SESSION_PREFIX,
        "user_peer_id": HONCHO_USER_PEER_ID,
        "assistant_peer_id": HONCHO_ASSISTANT_PEER_ID,
        "default_tokens": HONCHO_CONTEXT_TOKENS,
        "limit_to_session": HONCHO_LIMIT_TO_SESSION,
    }
    if not _honcho_enabled():
        status["available"] = False
        status["message"] = "Set CONTEXT_BROKER_CONTEXT_BACKEND=honcho to enable Honcho context."
        return status

    try:
        _get_honcho_client()
        status["available"] = True
        status["auth_verified"] = False
        status["message"] = "Honcho SDK is available; auth is verified on save/load."
    except Exception as e:
        status["available"] = False
        status["auth_verified"] = False
        status["message"] = str(e)
    return status


def save_honcho_chat_context(
    session_id: str,
    project_root: str = "",
    user_message: str = "",
    assistant_message: str = "",
    user_peer_id: str = "",
    assistant_peer_id: str = "",
) -> dict[str, Any]:
    """Persist chat turns to Honcho for cross-chat context retrieval."""
    client = _get_honcho_client()
    resolved_session_id = _honcho_session_id(session_id, project_root)
    user_id = _safe_id(resolve_user_peer_id(user_peer_id), HONCHO_USER_PEER_ID)
    assistant_id = _safe_id(assistant_peer_id, HONCHO_ASSISTANT_PEER_ID)

    session = client.session(resolved_session_id)
    user_peer = client.peer(user_id)
    assistant_peer = client.peer(assistant_id)

    messages = []
    if user_message:
        messages.append(user_peer.message(user_message))
    if assistant_message:
        messages.append(assistant_peer.message(assistant_message))
    if not messages:
        raise ValueError("At least one of user_message or assistant_message is required")

    session.add_messages(messages)

    # Mirror the same turn to the local JSON ledger so chats survive an
    # unreachable Honcho deployment and are auditable on disk.
    import time as _time

    now = _time.time()
    ledger_messages: list[dict[str, Any]] = []
    if user_message:
        ledger_messages.append({"peer_id": user_id, "content": user_message, "created_at": now})
    if assistant_message:
        ledger_messages.append(
            {"peer_id": assistant_id, "content": assistant_message, "created_at": now}
        )
    ledger_files = chat_ledger.append_turn(project_root, session_id, ledger_messages)

    return {
        "backend": "honcho",
        "session_id": resolved_session_id,
        "messages_saved": len(messages),
        "user_peer_id": user_id,
        "assistant_peer_id": assistant_id,
        "ledger_files": ledger_files,
    }


def _message_to_dict(message: Any) -> dict[str, Any]:
    """Convert Honcho message objects to JSON-safe dictionaries."""
    if isinstance(message, dict):
        return message
    payload: dict[str, Any] = {}
    for field in ("id", "content", "peer_id", "session_id", "created_at", "token_count"):
        value = getattr(message, field, None)
        if value is not None:
            payload[field] = value
    return payload


def _summary_to_dict(summary: Any) -> dict[str, Any] | None:
    """Convert a Honcho summary object to a JSON-safe dictionary."""
    if summary is None:
        return None
    if isinstance(summary, dict):
        return summary
    content = getattr(summary, "content", None)
    if content is None:
        return None
    return {
        "content": content,
        "summary_type": getattr(summary, "summary_type", None),
        "created_at": getattr(summary, "created_at", None),
    }


def load_honcho_chat_context(
    session_id: str,
    project_root: str = "",
    tokens: int = 0,
    summary: bool = True,
    search_query: str = "",
    limit_to_session: bool = HONCHO_LIMIT_TO_SESSION,
    user_peer_id: str = "",
    assistant_peer_id: str = "",
) -> dict[str, Any]:
    """Load Honcho session context in a JSON-safe shape."""
    client = _get_honcho_client()
    resolved_session_id = _honcho_session_id(session_id, project_root)
    assistant_id = _safe_id(assistant_peer_id, HONCHO_ASSISTANT_PEER_ID)
    user_id = _safe_id(resolve_user_peer_id(user_peer_id), HONCHO_USER_PEER_ID)

    session = client.session(resolved_session_id)
    assistant_peer = client.peer(assistant_id)
    token_budget = tokens if tokens > 0 else HONCHO_CONTEXT_TOKENS
    kwargs: dict[str, Any] = {"summary": summary, "tokens": token_budget}
    if search_query:
        kwargs.update(
            {
                "peer_target": user_id,
                "peer_perspective": assistant_id,
                "search_query": search_query,
                "limit_to_session": limit_to_session,
            }
        )
    elif limit_to_session:
        kwargs["limit_to_session"] = True

    if hasattr(session, "get_context"):
        context = session.get_context(**kwargs)
    else:
        context = session.context(**kwargs)

    openai_messages = []
    if hasattr(context, "to_openai"):
        try:
            openai_messages = context.to_openai(assistant=assistant_peer)
        except Exception:
            openai_messages = context.to_openai(assistant=assistant_id)

    messages = [_message_to_dict(message) for message in getattr(context, "messages", [])]
    return {
        "backend": "honcho",
        "session_id": resolved_session_id,
        "tokens": token_budget,
        "limit_to_session": limit_to_session,
        "summary": _summary_to_dict(getattr(context, "summary", None)),
        "messages": messages,
        "openai_messages": openai_messages,
        "peer_representation": getattr(context, "peer_representation", None),
        "peer_card": getattr(context, "peer_card", None),
    }


def dumps_context_payload(payload: dict[str, Any]) -> str:
    """Serialize context payloads with stable formatting for MCP responses."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
