"""
Cross-chat context MCP tool handlers.

Dispatches to either the Honcho or Redis context backend based on
CONTEXT_BROKER_CONTEXT_BACKEND.
"""

from fastmcp import Context, FastMCP

from context_broker.config import (
    AUTO_WARM_CACHE_ON_SAVE,
    CONTEXT_BACKEND,
    HONCHO_LIMIT_TO_SESSION,
)
from context_broker.context_ttc.tasks import chat_cache
from context_broker.context_ttc.tasks.redis_tasks import (
    list_users as redis_list_users,
    load_cross_session_matches,
    load_user_activity as redis_load_user_activity,
    project_digest as redis_project_digest,
)
from context_broker.identity import describe_user_identity
from context_broker.context_ttc.tasks.honcho_tasks import (
    dumps_context_payload,
    get_context_backend_status as honcho_status,
    load_honcho_chat_context,
    save_honcho_chat_context,
)
from context_broker.context_ttc.tasks.redis_tasks import (
    get_context_backend_status as redis_status,
    load_redis_chat_context,
    save_redis_chat_context,
)
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import notify_error, progress
from context_broker.utils import log


def _status() -> dict:
    """Return backend status for whichever backend is selected."""
    if CONTEXT_BACKEND == "redis":
        backend = redis_status()
    elif CONTEXT_BACKEND == "honcho":
        backend = honcho_status()
    else:
        backend = {
            "backend": CONTEXT_BACKEND,
            "enabled": False,
            "available": False,
            "message": "Set CONTEXT_BROKER_CONTEXT_BACKEND to 'honcho' or 'redis'.",
        }
    backend["chat_cache"] = chat_cache.status()
    backend["identity"] = describe_user_identity()
    return backend


def _cache_params(kwargs: dict) -> dict:
    """Subset of load kwargs that should key the chat cache."""
    return {
        "backend": CONTEXT_BACKEND,
        "tokens": kwargs.get("tokens", 0),
        "summary": kwargs.get("summary", True),
        "search_query": kwargs.get("search_query", ""),
        "limit_to_session": kwargs.get("limit_to_session", True),
        "user_peer_id": kwargs.get("user_peer_id", ""),
        "assistant_peer_id": kwargs.get("assistant_peer_id", ""),
    }


def _default_load_params() -> dict:
    """Default-params cache signature used to warm the cache on save."""
    return _cache_params({})


def _warm_session_cache(project_root: str, session_id: str) -> bool:
    """After a save, re-fetch the full session and write it to the cache under
    the default load signature. Returns True when the cache was warmed."""
    try:
        if CONTEXT_BACKEND == "redis":
            payload = load_redis_chat_context(
                session_id=session_id, project_root=project_root
            )
        elif CONTEXT_BACKEND == "honcho":
            payload = load_honcho_chat_context(
                session_id=session_id, project_root=project_root
            )
        else:
            return False
        return chat_cache.put(
            project_root, session_id, payload, **_default_load_params()
        )
    except Exception as e:
        log(f"chat cache warm-on-save skipped: {e}", "WARN")
        return False


def _save(warm_cache: bool = True, **kwargs) -> dict:
    """Dispatch save to the active backend, dual-write the ledger (done inside
    the backend save), invalidate prior cache entries, and — by default — warm
    the default-params cache signature with the full session so the next read
    is a cached hit instead of a miss-then-fill round trip.

    Batch callers (record_session) pass warm_cache=False per turn and warm
    once at the end, reporting the real outcome.
    """
    if CONTEXT_BACKEND == "redis":
        result = save_redis_chat_context(**kwargs)
    else:
        result = save_honcho_chat_context(**kwargs)

    project_root = kwargs.get("project_root", "")
    session_id = kwargs.get("session_id", "")
    # Always invalidate so parameterized reads (search_query, custom tokens, ...)
    # see the new turns.
    chat_cache.invalidate(project_root, session_id)
    if AUTO_WARM_CACHE_ON_SAVE and warm_cache:
        result["cache_warmed"] = _warm_session_cache(project_root, session_id)
    else:
        result["cache_warmed"] = False
    return result


def _load(**kwargs) -> dict:
    """Dispatch load to the active backend, with a Redis read-through cache."""
    project_root = kwargs.get("project_root", "")
    session_id = kwargs.get("session_id", "")
    params = _cache_params(kwargs)

    cached = chat_cache.get(project_root, session_id, **params)
    if cached is not None:
        cached["cached"] = True
        return cached

    if CONTEXT_BACKEND == "redis":
        payload = load_redis_chat_context(**kwargs)
    else:
        payload = load_honcho_chat_context(**kwargs)
    chat_cache.put(project_root, session_id, payload, **params)
    payload["cached"] = False
    return payload


def register_context_tools(mcp: FastMCP) -> None:
    """Register cross-chat context tools."""

    @mcp.tool()
    async def context_backend_status(ctx: Context = None) -> str:
        """Show configured cross-chat context backend status."""
        with tracked_activity():
            await progress(ctx, "Checking cross-chat context backend status")
            return dumps_context_payload(_status())

    @mcp.tool()
    async def save_chat_context(
        session_id: str,
        user_message: str = "",
        assistant_message: str = "",
        project_root: str = "",
        user_peer_id: str = "",
        assistant_peer_id: str = "",
        ctx: Context = None,
    ) -> str:
        """Save chat messages to the configured cross-chat context backend."""
        with tracked_activity():
            if not session_id:
                return "Error: session_id is required"
            root = resolve_project_root(project_root) if project_root else ""
            await progress(ctx, f"Saving chat context for session: {session_id}")
            try:
                payload = _save(
                    session_id=session_id,
                    project_root=root,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    user_peer_id=user_peer_id,
                    assistant_peer_id=assistant_peer_id,
                )
                log(f"Saved {payload['messages_saved']} {payload['backend']} messages")
                return dumps_context_payload(payload)
            except Exception as e:
                error_msg = f"Context save error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"

    @mcp.tool()
    async def record_session(
        session_id: str,
        turns: list[dict] = None,
        project_root: str = "",
        user_peer_id: str = "",
        assistant_peer_id: str = "",
        ctx: Context = None,
    ) -> str:
        """Persist an ENTIRE chat history in one call.

        ``turns`` is a list of ``{"user": "...", "assistant": "..."}`` dicts in
        chronological order — pass every exchange you have. Each turn is
        appended to the session (never overwriting prior turns), mirrored to the
        local JSON ledger, and the chat cache is warmed at the end so the next
        load is an immediate cached hit.

        Prefer this over a flurry of ``record_turn`` calls when you have the
        full conversation in context (e.g. when the user asks you to save the
        whole chat).
        """
        with tracked_activity():
            if not session_id:
                return "Error: session_id is required"
            if not turns:
                return "Error: turns must be a non-empty list of {user, assistant} dicts"
            root = resolve_project_root(project_root) if project_root else ""
            await progress(ctx, f"Recording session ({len(turns)} turn(s)): {session_id}")

            total_saved = 0
            ledger_files: list[str] = []
            backend_label = CONTEXT_BACKEND
            try:
                # Validate the ENTIRE batch before writing anything, so a
                # malformed turn can never leave a partially committed session.
                prepared: list[tuple[str, str]] = []
                for index, turn in enumerate(turns):
                    if not isinstance(turn, dict):
                        return f"Error: turns[{index}] is not an object"
                    user_msg = str(turn.get("user", "") or "")
                    assistant_msg = str(turn.get("assistant", "") or "")
                    if user_msg or assistant_msg:
                        prepared.append((user_msg, assistant_msg))
                if not prepared:
                    return "Error: every turn is empty — nothing to record"

                for user_msg, assistant_msg in prepared:
                    payload = _save(
                        session_id=session_id,
                        project_root=root,
                        user_message=user_msg,
                        assistant_message=assistant_msg,
                        user_peer_id=user_peer_id,
                        assistant_peer_id=assistant_peer_id,
                        warm_cache=False,
                    )
                    total_saved += int(payload.get("messages_saved", 0))
                    backend_label = payload.get("backend", backend_label)
                    for path in payload.get("ledger_files", []):
                        if path not in ledger_files:
                            ledger_files.append(path)

                # Warm the cache once for the whole batch, per the API contract.
                cache_warmed = (
                    _warm_session_cache(root, session_id) if AUTO_WARM_CACHE_ON_SAVE else False
                )
                log(
                    f"record_session persisted {total_saved} messages "
                    f"across {len(prepared)} turn(s) into '{session_id}' "
                    f"({backend_label}; cache warmed: {cache_warmed})"
                )
                return dumps_context_payload(
                    {
                        "backend": backend_label,
                        "session_id": session_id,
                        "turns_recorded": len(prepared),
                        "turns_skipped": len(turns) - len(prepared),
                        "messages_saved": total_saved,
                        "ledger_files": ledger_files,
                        "cache_warmed": cache_warmed,
                    }
                )
            except Exception as e:
                error_msg = f"record_session error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"

    @mcp.tool()
    async def record_turn(
        session_id: str,
        user_message: str = "",
        assistant_message: str = "",
        project_root: str = "",
        user_peer_id: str = "",
        assistant_peer_id: str = "",
        ctx: Context = None,
    ) -> str:
        """Persist the most recent (user, assistant) exchange.

        Call this after EVERY response you give in a conversation, with the
        user's question and your reply, so the chat history accumulates across
        sessions. Each call APPENDS — prior turns are never overwritten. The
        same exchange is mirrored to a local JSON ledger under .context-broker/
        chats/, and the chat cache is warmed automatically so the next
        load_chat_context is a cached hit.

        Use a stable ``session_id`` per conversation (e.g. the editor's chat id
        or the date). Different conversations should use different session_ids.
        For dumping an entire conversation at once, prefer ``record_session``.
        """
        with tracked_activity():
            if not session_id:
                return "Error: session_id is required"
            if not (user_message or assistant_message):
                return "Error: at least one of user_message or assistant_message is required"
            root = resolve_project_root(project_root) if project_root else ""
            await progress(ctx, f"Recording turn into session: {session_id}")
            try:
                payload = _save(
                    session_id=session_id,
                    project_root=root,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    user_peer_id=user_peer_id,
                    assistant_peer_id=assistant_peer_id,
                )
                log(
                    f"record_turn appended {payload['messages_saved']} "
                    f"{payload['backend']} messages "
                    f"(ledger: {len(payload.get('ledger_files', []))} file(s))"
                )
                return dumps_context_payload(payload)
            except Exception as e:
                error_msg = f"record_turn error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"

    @mcp.tool()
    async def list_user_activity(
        project_root: str = "",
        peer_id: str = "",
        limit: int = 100,
        ctx: Context = None,
    ) -> str:
        """Show when each user last asked something in this project.

        Without ``peer_id``: returns the per-user summary list — peer_id,
        first_seen, last_seen, request_count for everyone who has talked in
        this project. With ``peer_id``: returns that user's full audit log,
        i.e. the last ``limit`` requests as {timestamp, session_id} entries.
        Requires CONTEXT_BROKER_CONTEXT_BACKEND=redis.
        """
        with tracked_activity():
            if CONTEXT_BACKEND != "redis":
                return (
                    "Error: list_user_activity requires "
                    "CONTEXT_BROKER_CONTEXT_BACKEND=redis "
                    f"(current backend: {CONTEXT_BACKEND!r})."
                )
            root = resolve_project_root(project_root) if project_root else ""
            digest = redis_project_digest(root)
            await progress(
                ctx,
                f"Loading user activity for {peer_id or 'all users'} in {digest}",
            )
            try:
                if peer_id:
                    payload = redis_load_user_activity(digest, peer_id, limit=limit)
                    payload["project_root"] = root
                else:
                    payload = {
                        "project_digest": digest,
                        "project_root": root,
                        "users": redis_list_users(digest),
                    }
                return dumps_context_payload(payload)
            except Exception as e:
                error_msg = f"list_user_activity error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"

    @mcp.tool()
    async def load_cross_session_context(
        project_root: str = "",
        search_query: str = "",
        top_k: int = 10,
        per_session_limit: int = 50,
        ctx: Context = None,
    ) -> str:
        """Search every session of one project and return the most important
        matching turns across all of them.

        "Important" means: messages whose content matches ``search_query`` (case-
        insensitive substring), ranked by recency descending. Each result is
        annotated with the originating ``session_id`` so the dashboard can
        deep-link back. Requires CONTEXT_BROKER_CONTEXT_BACKEND=redis.
        """
        with tracked_activity():
            if CONTEXT_BACKEND != "redis":
                return (
                    "Error: load_cross_session_context requires "
                    "CONTEXT_BROKER_CONTEXT_BACKEND=redis "
                    f"(current backend: {CONTEXT_BACKEND!r})."
                )
            root = resolve_project_root(project_root) if project_root else ""
            await progress(ctx, f"Cross-session search for: {search_query!r}")
            try:
                payload = load_cross_session_matches(
                    project_root=root,
                    search_query=search_query,
                    top_k=top_k,
                    per_session_limit=per_session_limit,
                )
                return dumps_context_payload(payload)
            except Exception as e:
                error_msg = f"Cross-session load error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"

    @mcp.tool()
    async def load_chat_context(
        session_id: str,
        project_root: str = "",
        tokens: int = 0,
        summary: bool = True,
        search_query: str = "",
        limit_to_session: bool = HONCHO_LIMIT_TO_SESSION,
        user_peer_id: str = "",
        assistant_peer_id: str = "",
        ctx: Context = None,
    ) -> str:
        """Load cross-chat context from the configured context backend."""
        with tracked_activity():
            if not session_id:
                return "Error: session_id is required"
            root = resolve_project_root(project_root) if project_root else ""
            await progress(ctx, f"Loading chat context for session: {session_id}")
            try:
                payload = _load(
                    session_id=session_id,
                    project_root=root,
                    tokens=tokens,
                    summary=summary,
                    search_query=search_query,
                    limit_to_session=limit_to_session,
                    user_peer_id=user_peer_id,
                    assistant_peer_id=assistant_peer_id,
                )
                return dumps_context_payload(payload)
            except Exception as e:
                error_msg = f"Context load error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {e}"
