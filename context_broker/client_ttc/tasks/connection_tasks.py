"""Downstream MCP connection manager for Universal Context Router."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncContextManager, cast

from context_broker.client_ttc.tools.contract_tools import (
    ConnectionState,
    DownstreamCallResult,
    DownstreamCapabilities,
    DownstreamPrompt,
    DownstreamResource,
    DownstreamServerConfig,
    DownstreamTool,
)
from context_broker.client_ttc.tools.transport_tools import open_downstream_session
from context_broker.utils import log

SessionFactory = Callable[[DownstreamServerConfig], AsyncContextManager[Any]]


def _obj_get(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute from SDK models or dict-like test doubles."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _tools_from_result(server: str, result: Any) -> list[DownstreamTool]:
    tools = _obj_get(result, "tools", []) or []
    return [
        DownstreamTool(
            server=server,
            name=str(_obj_get(tool, "name", "")),
            description=str(_obj_get(tool, "description", "") or ""),
            input_schema=_as_dict(_obj_get(tool, "inputSchema", None) or _obj_get(tool, "input_schema", None)),
        )
        for tool in tools
        if _obj_get(tool, "name", None)
    ]


def _prompts_from_result(server: str, result: Any) -> list[DownstreamPrompt]:
    prompts = _obj_get(result, "prompts", []) or []
    return [
        DownstreamPrompt(
            server=server,
            name=str(_obj_get(prompt, "name", "")),
            description=str(_obj_get(prompt, "description", "") or ""),
            arguments=list(_obj_get(prompt, "arguments", []) or []),
        )
        for prompt in prompts
        if _obj_get(prompt, "name", None)
    ]


def _resources_from_result(server: str, result: Any) -> list[DownstreamResource]:
    resources = _obj_get(result, "resources", []) or []
    return [
        DownstreamResource(
            server=server,
            uri=str(_obj_get(resource, "uri", "")),
            name=str(_obj_get(resource, "name", "") or ""),
            description=str(_obj_get(resource, "description", "") or ""),
            mime_type=_obj_get(resource, "mimeType", None) or _obj_get(resource, "mime_type", None),
        )
        for resource in resources
        if _obj_get(resource, "uri", None)
    ]


@dataclass
class ManagedDownstreamConnection:
    """Lifecycle wrapper for one downstream MCP server."""

    config: DownstreamServerConfig
    session_factory: SessionFactory = open_downstream_session
    state: ConnectionState = ConnectionState.DISCONNECTED
    capabilities: DownstreamCapabilities | None = None
    last_error: str | None = None
    reconnect_count: int = 0
    _session_cm: AsyncContextManager[Any] | None = field(default=None, init=False, repr=False)
    _session: Any | None = field(default=None, init=False, repr=False)

    async def connect(self) -> DownstreamCapabilities:
        """Connect, initialize, and discover downstream capabilities."""
        self.config.validate()
        self.state = ConnectionState.CONNECTING
        self.last_error = None
        attempt = 0
        while True:
            try:
                self._session_cm = self.session_factory(self.config)
                self._session = await self._session_cm.__aenter__()
                self.capabilities = await self.discover_capabilities()
                self.state = ConnectionState.READY
                return self.capabilities
            except Exception as exc:
                self.last_error = str(exc)
                await self.disconnect()
                if attempt >= self.config.reconnect_attempts:
                    self.state = ConnectionState.FAILED
                    raise
                attempt += 1
                self.reconnect_count += 1
                await asyncio.sleep(self.config.reconnect_backoff_seconds * attempt)

    async def disconnect(self) -> None:
        """Close the active session if one exists."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as exc:  # pragma: no cover - defensive cleanup logging
                log(f"⚠️ Downstream MCP close failed for {self.config.name}: {exc}", "WARN")
        self._session_cm = None
        self._session = None
        if self.state != ConnectionState.FAILED:
            self.state = ConnectionState.DISCONNECTED

    async def ensure_ready(self) -> None:
        """Reconnect when no usable session is present."""
        if self._session is None or self.state != ConnectionState.READY:
            await self.connect()

    async def discover_capabilities(self) -> DownstreamCapabilities:
        """Run capability discovery against the active MCP session."""
        if self._session is None:
            raise RuntimeError("downstream session is not connected")
        tools_result = await self._session.list_tools()
        prompts_result = await self._session.list_prompts()
        resources_result = await self._session.list_resources()
        capabilities = DownstreamCapabilities(
            server=self.config.name,
            tools=_tools_from_result(self.config.name, tools_result),
            prompts=_prompts_from_result(self.config.name, prompts_result),
            resources=_resources_from_result(self.config.name, resources_result),
            raw={
                "tools": _as_dict(tools_result),
                "prompts": _as_dict(prompts_result),
                "resources": _as_dict(resources_result),
            },
        )
        self.capabilities = capabilities
        return capabilities

    async def heartbeat(self) -> bool:
        """Return True when the downstream server responds to a lightweight probe."""
        try:
            await self.ensure_ready()
            if self._session is None:
                return False
            await self._session.list_tools()
            self.state = ConnectionState.READY
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.state = ConnectionState.DEGRADED
            try:
                await self.connect()
                return True
            except Exception:
                return False

    async def list_tools(self) -> list[DownstreamTool]:
        """List downstream tools, using cached discovery unless absent."""
        await self.ensure_ready()
        if self.capabilities is None:
            await self.discover_capabilities()
        return list(self.capabilities.tools if self.capabilities else [])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> DownstreamCallResult:
        """Call a downstream MCP tool through the active session."""
        await self.ensure_ready()
        if self._session is None:
            raise RuntimeError("downstream session is not connected")
        result = await self._session.call_tool(name, arguments or {})
        return DownstreamCallResult(
            server=self.config.name,
            tool=name,
            ok=not bool(_obj_get(result, "isError", False) or _obj_get(result, "is_error", False)),
            is_error=bool(_obj_get(result, "isError", False) or _obj_get(result, "is_error", False)),
            content=_obj_get(result, "content", result),
        )


class DownstreamConnectionManager:
    """Registry and connection manager for downstream MCP servers."""

    def __init__(self, session_factory: SessionFactory = open_downstream_session) -> None:
        self.session_factory = session_factory
        self._connections: dict[str, ManagedDownstreamConnection] = {}

    def register(self, config: DownstreamServerConfig) -> ManagedDownstreamConnection:
        """Register or replace one downstream server config."""
        config.validate()
        connection = ManagedDownstreamConnection(config, self.session_factory)
        self._connections[config.name] = connection
        return connection

    def get(self, server: str) -> ManagedDownstreamConnection | None:
        """Return a managed connection by server name."""
        return self._connections.get(server)

    def all(self) -> list[ManagedDownstreamConnection]:
        """Return all managed connections in deterministic order."""
        return [self._connections[name] for name in sorted(self._connections)]

    async def connect_all(self) -> dict[str, dict[str, Any]]:
        """Connect to every registered downstream server in parallel."""
        results = await asyncio.gather(
            *(connection.connect() for connection in self.all()),
            return_exceptions=True,
        )
        output: dict[str, dict[str, Any]] = {}
        for connection, result in zip(self.all(), results, strict=True):
            if isinstance(result, Exception):
                output[connection.config.name] = {
                    "state": connection.state.value,
                    "error": str(result),
                }
            else:
                capabilities = cast(DownstreamCapabilities, result)
                output[connection.config.name] = {
                    "state": connection.state.value,
                    "capabilities": capabilities.to_dict(),
                }
        return output

    async def discover_all(self) -> dict[str, dict[str, Any]]:
        """Return capability discovery for all registered downstream servers."""
        await self.connect_all()
        return {
            connection.config.name: (
                connection.capabilities.to_dict() if connection.capabilities else {"server": connection.config.name}
            )
            for connection in self.all()
        }

    async def heartbeat_all(self) -> dict[str, bool]:
        """Heartbeat all registered downstream servers in parallel."""
        results = await asyncio.gather(
            *(connection.heartbeat() for connection in self.all()),
            return_exceptions=True,
        )
        return {
            connection.config.name: bool(result) if not isinstance(result, Exception) else False
            for connection, result in zip(self.all(), results, strict=True)
        }

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> DownstreamCallResult:
        """Call a named tool on a named downstream server."""
        connection = self.get(server)
        if connection is None:
            raise KeyError(f"unknown downstream server: {server}")
        return await connection.call_tool(tool, arguments)


@asynccontextmanager
async def managed_downstream_manager(
    configs: list[DownstreamServerConfig],
    session_factory: SessionFactory = open_downstream_session,
) -> AsyncIterator[DownstreamConnectionManager]:
    """Context manager that disconnects all downstream sessions on exit."""
    manager = DownstreamConnectionManager(session_factory=session_factory)
    for config in configs:
        manager.register(config)
    try:
        yield manager
    finally:
        await asyncio.gather(*(connection.disconnect() for connection in manager.all()))
