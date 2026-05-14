"""
Backend-agnostic data access for the dashboard.

Returns project / session / message data for whichever cross-chat context
backend is active. Redis is the primary supported backend; Honcho data is
only browsable in a limited way (session ids must be provided explicitly).
"""

from typing import Any

from context_broker.config import CONTEXT_BACKEND
from context_broker.context_ttc.tasks import redis_tasks


class DashboardError(RuntimeError):
    """Raised when the dashboard cannot service a request."""


def active_backend() -> str:
    """Return the configured cross-chat context backend."""
    return CONTEXT_BACKEND


def list_projects() -> list[dict[str, Any]]:
    """List projects with stored cross-chat context."""
    if CONTEXT_BACKEND == "redis":
        return redis_tasks.list_projects()
    raise DashboardError(
        "Browsing all projects is only supported when "
        "CONTEXT_BROKER_CONTEXT_BACKEND=redis. "
        f"Current backend: {CONTEXT_BACKEND!r}."
    )


def list_sessions(digest: str) -> list[dict[str, Any]]:
    """List sessions for one project digest."""
    if CONTEXT_BACKEND == "redis":
        return redis_tasks.list_sessions(digest)
    raise DashboardError(
        "Listing sessions requires CONTEXT_BROKER_CONTEXT_BACKEND=redis."
    )


def load_session(digest: str, session_id: str) -> dict[str, Any]:
    """Load one (project, session) pair."""
    if CONTEXT_BACKEND == "redis":
        return redis_tasks.load_session(digest, session_id)
    raise DashboardError(
        "Loading sessions requires CONTEXT_BROKER_CONTEXT_BACKEND=redis."
    )


def list_users(digest: str) -> list[dict[str, Any]]:
    """Per-project user activity summaries."""
    if CONTEXT_BACKEND == "redis":
        return redis_tasks.list_users(digest)
    raise DashboardError(
        "Listing users requires CONTEXT_BROKER_CONTEXT_BACKEND=redis."
    )


def load_user_activity(digest: str, peer_id: str, limit: int = 100) -> dict[str, Any]:
    """Full per-user audit trail."""
    if CONTEXT_BACKEND == "redis":
        return redis_tasks.load_user_activity(digest, peer_id, limit=limit)
    raise DashboardError(
        "Loading user activity requires CONTEXT_BROKER_CONTEXT_BACKEND=redis."
    )
