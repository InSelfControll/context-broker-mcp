"""Typed contracts for downstream MCP client connections."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import re
from typing import Any

_DOWNSTREAM_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_downstream_identity(value: str, *, kind: str) -> str:
    """Return a canonical server or tool name, rejecting ambiguous identifiers."""
    if not _DOWNSTREAM_IDENTITY_RE.fullmatch(value):
        raise ValueError(
            f"downstream {kind} must use a canonical 1-64 character "
            "alphanumeric, underscore, or hyphen identity"
        )
    return value


class DownstreamTransport(StrEnum):
    """Supported downstream MCP transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class ConnectionState(StrEnum):
    """Lifecycle states for one downstream MCP connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class DownstreamServerConfig:
    """Configuration for one downstream MCP server."""

    name: str
    transport: DownstreamTransport
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    heartbeat_interval_seconds: float = 30.0
    reconnect_attempts: int = 3
    reconnect_backoff_seconds: float = 0.25

    def validate(self) -> None:
        """Validate transport-specific config without opening a connection."""
        if not self.name.strip():
            raise ValueError("downstream server name is required")
        if self.transport == DownstreamTransport.STDIO and not self.command:
            raise ValueError("stdio downstream server requires command")
        if self.transport in {DownstreamTransport.HTTP, DownstreamTransport.SSE} and not self.url:
            raise ValueError(f"{self.transport.value} downstream server requires url")
        if self.transport == DownstreamTransport.STDIO and self.url:
            raise ValueError("stdio downstream server must not set url")
        if self.transport in {DownstreamTransport.HTTP, DownstreamTransport.SSE} and self.command:
            raise ValueError(f"{self.transport.value} downstream server must not set command")


@dataclass(frozen=True)
class DownstreamTool:
    """Public descriptor for a tool discovered from a downstream MCP server."""

    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Return globally unique registry id for this downstream tool."""
        return f"{self.server}.{self.name}"

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable descriptor."""
        payload = asdict(self)
        payload["id"] = self.id
        return payload


@dataclass(frozen=True)
class DownstreamPrompt:
    """Public descriptor for a prompt discovered from a downstream MCP server."""

    server: str
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable descriptor."""
        return asdict(self)


@dataclass(frozen=True)
class DownstreamResource:
    """Public descriptor for a resource discovered from a downstream MCP server."""

    server: str
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable descriptor."""
        return asdict(self)


@dataclass(frozen=True)
class DownstreamCapabilities:
    """Capabilities discovered from one downstream MCP server."""

    server: str
    tools: list[DownstreamTool] = field(default_factory=list)
    prompts: list[DownstreamPrompt] = field(default_factory=list)
    resources: list[DownstreamResource] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable discovery result."""
        return {
            "server": self.server,
            "tools": [tool.to_dict() for tool in self.tools],
            "prompts": [prompt.to_dict() for prompt in self.prompts],
            "resources": [resource.to_dict() for resource in self.resources],
            "raw": self.raw,
        }


@dataclass(frozen=True)
class DownstreamCallResult:
    """Result from calling a downstream MCP tool."""

    server: str
    tool: str
    ok: bool
    content: Any
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable call result."""
        return asdict(self)
