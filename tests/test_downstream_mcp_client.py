"""Tests for downstream MCP client subsystem."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from context_broker.client_ttc.codebase.api import (
    ConnectionState,
    DownstreamConnectionManager,
    DownstreamServerConfig,
    DownstreamTransport,
    filtered_stdio_env,
)


class FakeSession:
    """Small MCP ClientSession test double."""

    def __init__(self) -> None:
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.list_tools_calls = 0

    async def list_tools(self) -> Any:
        self.list_tools_calls += 1
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="search",
                    description="search downstream context",
                    inputSchema={"type": "object"},
                )
            ]
        )

    async def list_prompts(self) -> Any:
        return SimpleNamespace(
            prompts=[SimpleNamespace(name="summarize", description="Summarize context", arguments=[])]
        )

    async def list_resources(self) -> Any:
        return SimpleNamespace(
            resources=[
                SimpleNamespace(
                    uri="file:///tmp/example.md",
                    name="example",
                    description="Example resource",
                    mimeType="text/markdown",
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.tool_calls.append((name, arguments))
        return SimpleNamespace(content=[{"type": "text", "text": "ok"}], isError=False)


def test_downstream_config_validation_requires_transport_specific_fields() -> None:
    cfg = DownstreamServerConfig(name="ctx7", transport=DownstreamTransport.STDIO, command="uvx")
    cfg.validate()

    missing_command = DownstreamServerConfig(name="bad", transport=DownstreamTransport.STDIO)
    try:
        missing_command.validate()
    except ValueError as exc:
        assert "requires command" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("stdio config without command should fail")

    missing_url = DownstreamServerConfig(name="bad", transport=DownstreamTransport.HTTP)
    try:
        missing_url.validate()
    except ValueError as exc:
        assert "requires url" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("http config without url should fail")


def test_filtered_stdio_env_does_not_inherit_secret_parent_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("API_KEY", "do-not-inherit")
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/cache")

    env = filtered_stdio_env({"EXPLICIT_TOKEN": "allowed"})

    assert env["PATH"] == "/bin"
    assert env["XDG_CACHE_HOME"] == "/tmp/cache"
    assert env["EXPLICIT_TOKEN"] == "allowed"
    assert "API_KEY" not in env


def test_connection_manager_discovers_capabilities_and_calls_tools() -> None:
    session = FakeSession()

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[FakeSession]:
        yield session

    async def run() -> None:
        manager = DownstreamConnectionManager(session_factory=fake_factory)
        manager.register(
            DownstreamServerConfig(
                name="context7",
                transport=DownstreamTransport.SSE,
                url="http://localhost:8765/sse",
            )
        )

        discovery = await manager.discover_all()
        assert discovery["context7"]["tools"][0]["id"] == "context7.search"
        assert discovery["context7"]["prompts"][0]["name"] == "summarize"
        assert discovery["context7"]["resources"][0]["uri"] == "file:///tmp/example.md"

        result = await manager.call_tool("context7", "search", {"query": "auth"})
        assert result.ok is True
        assert session.tool_calls == [("search", {"query": "auth"})]

    asyncio.run(run())


def test_connection_reconnects_after_transient_failure() -> None:
    session = FakeSession()
    attempts = {"count": 0}

    @asynccontextmanager
    async def flaky_factory(_config: DownstreamServerConfig) -> AsyncIterator[FakeSession]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary outage")
        yield session

    async def run() -> None:
        manager = DownstreamConnectionManager(session_factory=flaky_factory)
        connection = manager.register(
            DownstreamServerConfig(
                name="github",
                transport=DownstreamTransport.HTTP,
                url="http://localhost:3000/mcp",
                reconnect_attempts=1,
                reconnect_backoff_seconds=0,
            )
        )

        await connection.connect()
        assert connection.state == ConnectionState.READY
        assert connection.reconnect_count == 1
        assert attempts["count"] == 2

    asyncio.run(run())
