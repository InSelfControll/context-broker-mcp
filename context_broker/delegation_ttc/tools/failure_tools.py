"""Safe, explicit failure records shared by delegation and MCP handlers."""

from pydantic import ValidationError


def failure(reason: str, *, code: str = "task_failed", **details) -> dict:
    """A failed task is never completed or eligible for automatic integration."""
    return {
        "status": "failed",
        "failure_code": code,
        "failure_reason": reason,
        "completed": False,
        "applied": False,
        "tests_executed": False,
        **details,
    }


def exception_reason(exc: Exception) -> str:
    """Keep useful validation locations without exposing rejected inputs or secrets."""
    if isinstance(exc, ValidationError):
        locations = [".".join(map(str, e["loc"])) for e in exc.errors(include_input=False)]
        return "Invalid agent/reviewer response fields: " + ", ".join(locations[:20])
    if isinstance(exc, OSError):
        return f"Project context could not be accessed (OS error {exc.errno})"
    return str(exc)
