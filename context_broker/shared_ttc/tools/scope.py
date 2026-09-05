"""Request-local project identity, propagated to worker threads by AnyIO."""

from contextvars import ContextVar

PROJECT_ROOT: ContextVar[str] = ContextVar("broker_project_root", default="")
PROJECT_HEADER = "x-context-broker-project-root"
