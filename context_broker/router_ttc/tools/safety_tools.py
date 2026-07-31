"""Safety checks for UCR tool routing and execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any

from context_broker.router_ttc.tools.registry_tools import ToolDescriptor
from context_broker.security_ttc.tools import _scan_content_for_secrets, is_secret_file


class SafetyDecision(StrEnum):
    """Possible safety outcomes for a selected tool call."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"


@dataclass(frozen=True)
class SafetyResult:
    """Detailed safety decision."""

    decision: SafetyDecision
    reason: str
    findings: list[str]


_DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+(/|~|\*)"),
    re.compile(r"\bmkfs(\.|\s)"),
    re.compile(r"\bdd\s+.*\bof=/dev/"),
    re.compile(r">\s*/dev/sd[a-z]"),
    re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b"),
    re.compile(r"\bchmod\s+-R\s+777\s+(/|~)"),
    re.compile(r"\bcurl\b.*\|\s*(sh|bash)"),
    re.compile(r"\bwget\b.*\|\s*(sh|bash)"),
]
_PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "you are now",
]
_PATH_TRAVERSAL_RE = re.compile(r"(^|/)\.\.(/|$)")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+)[a-z0-9._\-]+|"
    r"(sk-[a-z0-9_\-]{8,})|"
    r"(gh[pousr]_[a-z0-9_]{8,})|"
    r"((api[_-]?key|token|secret|password)\s*[:=]\s*)\S+"
)


def _flatten_values(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        values: list[str] = []
        for value in payload.values():
            values.extend(_flatten_values(value))
        return values
    if isinstance(payload, list | tuple | set):
        values = []
        for value in payload:
            values.extend(_flatten_values(value))
        return values
    if payload is None:
        return []
    return [str(payload)]


def _looks_like_path(key: str, value: str) -> bool:
    lowered = key.lower()
    return lowered in {"path", "file", "filename", "project_root", "root"} or "/" in value


def redact_secrets(value: Any) -> Any:
    """Redact secret-like strings recursively before returning tool outputs."""
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if not isinstance(value, str):
        return value

    def replacement(match: re.Match[str]) -> str:
        text = match.group(0)
        if text.lower().startswith("bearer "):
            return "Bearer [REDACTED]"
        if "=" in text:
            return text.split("=", 1)[0] + "=[REDACTED]"
        if ":" in text:
            return text.split(":", 1)[0] + ": [REDACTED]"
        return "[REDACTED]"

    return _SECRET_VALUE_RE.sub(replacement, value)


def assess_tool_execution(descriptor: ToolDescriptor, arguments: dict[str, Any]) -> SafetyResult:
    """Assess whether a tool can execute without leaking secrets or causing harm."""
    findings: list[str] = []
    blocked = False

    for key, raw_value in arguments.items():
        for value in _flatten_values(raw_value):
            lowered = value.lower()
            if any(pattern in lowered for pattern in _PROMPT_INJECTION_PATTERNS):
                findings.append("prompt injection text detected")
                blocked = True
            if _looks_like_path(key, value):
                rel_path = value.lstrip("/")
                secret, reason = is_secret_file(value, rel_path)
                if secret:
                    findings.append(reason)
                    blocked = True
                if _PATH_TRAVERSAL_RE.search(value):
                    findings.append("path traversal detected")
                    blocked = True
            if descriptor.shell_capable and key.lower() in {"command", "cmd", "shell"}:
                if any(pattern.search(value) for pattern in _DANGEROUS_COMMAND_PATTERNS):
                    findings.append("dangerous command detected")
                    blocked = True
            secret_content, secret_reason = _scan_content_for_secrets(value)
            if secret_content:
                findings.append(f"secret-like argument content: {secret_reason}")
                blocked = True

    if blocked:
        return SafetyResult(SafetyDecision.BLOCK, "; ".join(sorted(set(findings))), findings)

    if descriptor.risk_level.lower() in {"medium"}:
        return SafetyResult(SafetyDecision.CONFIRM, "medium-risk tool requires confirmation", findings)
    if descriptor.risk_level.lower() in {"high", "critical"} or descriptor.shell_capable:
        return SafetyResult(
            SafetyDecision.CONFIRM,
            "high-risk or shell-capable tool requires explicit confirmation",
            findings,
        )

    return SafetyResult(SafetyDecision.ALLOW, "safe to execute", findings)
