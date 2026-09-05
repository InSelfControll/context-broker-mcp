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
            arguments=[_as_dict(arg) for arg in (_obj_get(prompt, "arguments", []) or [])],
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
    _session: Any | None = field(default=None, init=False, repr=False)
    _session_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _session_stop: asyncio.Event | None = field(default=None, init=False, repr=False)
    _lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def connect(self) -> DownstreamCapabilities:
        """Connect, initialize, and discover downstream capabilities."""
        self.config.validate()
        async with self._lifecycle_lock:
            if self.state == ConnectionState.READY and self._session is not None:
                return cast(DownstreamCapabilities, self.capabilities)
            return await self._connect_locked()

    async def _serve_session(
        self, ready: asyncio.Future[DownstreamCapabilities], stop: asyncio.Event
    ) -> None:
        """Own both entry and exit of the SDK's task-local cancellation scopes."""
        try:
            async with self.session_factory(self.config) as session:
                self._session = session
                capabilities = await self.discover_capabilities()
                ready.set_result(capabilities)
                await stop.wait()
        except Exception as exc:
            self.last_error = str(exc)
            if not ready.done():
                ready.set_exception(exc)
        finally:
            self._session = None
            self.capabilities = None
            if not ready.done():
                ready.cancel()
            if self.state == ConnectionState.READY:
                self.state = ConnectionState.DISCONNECTED

    async def _connect_locked(self) -> DownstreamCapabilities:
        await self._close_session()
        self.state = ConnectionState.CONNECTING
        self.last_error = None
        attempt = 0
        while True:
            try:
                ready = asyncio.get_running_loop().create_future()
                self._session_stop = asyncio.Event()
                self._session_task = asyncio.create_task(
                    self._serve_session(ready, self._session_stop)
                )
                self.capabilities = await asyncio.wait_for(ready, self.config.timeout_seconds)
                self.state = ConnectionState.READY
                return self.capabilities
            except asyncio.CancelledError:
                await self._close_session()
                self.state = ConnectionState.DISCONNECTED
                raise
            except Exception as exc:
                self.last_error = str(exc)
                await self._close_session()
                if attempt >= self.config.reconnect_attempts:
                    self.state = ConnectionState.FAILED
                    raise
                attempt += 1
                self.reconnect_count += 1
                await asyncio.sleep(self.config.reconnect_backoff_seconds * attempt)

    async def disconnect(self) -> None:
        """Close the active session if one exists."""
        async with self._lifecycle_lock:
            await self._close_session()
            self.state = ConnectionState.DISCONNECTED

    async def _close_session(self) -> None:
        if self._session_stop is not None:
            self._session_stop.set()
        if self._session_task is not None:
            if self.state == ConnectionState.CONNECTING:
                self._session_task.cancel()
            try:
                await asyncio.wait_for(self._session_task, self.config.timeout_seconds)
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pragma: no cover - defensive cleanup
                log(f"⚠️ Downstream MCP close failed for {self.config.name}: {exc}", "WARN")
        self._session_task = None
        self._session_stop = None
        self._session = None
        self.capabilities = None

    async def ensure_ready(self) -> None:
        """Reconnect when no usable session is present."""
        if self._session is None or self.state != ConnectionState.READY:
            await self.connect()

    async def discover_capabilities(self) -> DownstreamCapabilities:
        """Run capability discovery against the active MCP session."""
        if self._session is None:
            raise RuntimeError("downstream session is not connected")
        tools_result = await self._list_capability("tools")
        prompts_result = await self._list_capability("prompts")
        resources_result = await self._list_capability("resources")
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

    async def _list_capability(self, kind: str) -> dict[str, Any]:
        getter = getattr(self._session, "get_server_capabilities", None)
        advertised = getter() if callable(getter) else None
        if advertised is not None and _obj_get(advertised, kind) is None:
            return {kind: []}
        method = getattr(self._session, f"list_{kind}")
        items: list[Any] = []
        cursor = None
        seen: set[str] = set()
        while True:
            page = await method(cursor=cursor) if cursor is not None else await method()
            items.extend(_obj_get(page, kind, []) or [])
            cursor = _obj_get(page, "nextCursor")
            if not cursor:
                return {kind: [_as_dict(item) for item in items]}
            if cursor in seen:
                raise RuntimeError(f"downstream {kind} discovery repeated a pagination cursor")
            seen.add(cursor)

    async def heartbeat(self) -> bool:
        """Return True when the downstream server responds to a lightweight probe."""
        try:
            await self.ensure_ready()
            if self._session is None:
                return False
            ping = getattr(self._session, "send_ping", None)
            if callable(ping):
                await asyncio.wait_for(ping(), self.config.timeout_seconds)
            else:
                await asyncio.wait_for(self._list_capability("tools"), self.config.timeout_seconds)
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
        result = await asyncio.wait_for(
            self._session.call_tool(name, arguments or {}), self.config.timeout_seconds
        )
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
        existing = self._connections.get(config.name)
        if existing is not None:
            if existing.config == config:
                return existing
            if existing._session_task is not None:
                raise ValueError("disconnect the downstream server before replacing its config")
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
        connections = self.all()
        results = await asyncio.gather(
            *(connection.connect() for connection in connections),
            return_exceptions=True,
        )
        output: dict[str, dict[str, Any]] = {}
        for connection, result in zip(connections, results, strict=True):
            if isinstance(result, BaseException):
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
        connections = self.all()
        results = await asyncio.gather(
            *(connection.heartbeat() for connection in connections),
            return_exceptions=True,
        )
        return {
            connection.config.name: bool(result) if not isinstance(result, BaseException) else False
            for connection, result in zip(connections, results, strict=True)
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
