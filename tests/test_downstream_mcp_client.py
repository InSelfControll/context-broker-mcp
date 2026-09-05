"""Tests for downstream MCP client subsystem."""

from __future__ import annotations

import asyncio
import pytest
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


def test_repeated_connect_keeps_one_session_and_disconnect_clears_discovery() -> None:
    opens = []
    closes = []

    @asynccontextmanager
    async def factory(config):
        opens.append(config.name)
        try:
            yield FakeSession()
        finally:
            closes.append(config.name)

    async def run():
        manager = DownstreamConnectionManager(session_factory=factory)
        connection = manager.register(
            DownstreamServerConfig(
                name="demo", transport=DownstreamTransport.STDIO, command="unused"
            )
        )
        await connection.connect()
        await connection.connect()
        assert opens == ["demo"]
        await connection.disconnect()
        assert closes == ["demo"]
        assert connection.capabilities is None

    asyncio.run(run())


def test_session_context_is_closed_in_the_task_that_opened_it() -> None:
    ownership = []

    @asynccontextmanager
    async def factory(_config):
        owner = asyncio.current_task()
        try:
            yield FakeSession()
        finally:
            ownership.append(owner is asyncio.current_task())

    async def run():
        manager = DownstreamConnectionManager(session_factory=factory)
        connection = manager.register(
            DownstreamServerConfig(
                name="demo", transport=DownstreamTransport.STDIO, command="unused"
            )
        )
        await manager.connect_all()
        await connection.disconnect()
        assert ownership == [True]

    asyncio.run(run())


def test_discovery_respects_optional_capabilities_and_pagination() -> None:
    class ToolsOnlySession(FakeSession):
        def get_server_capabilities(self):
            return SimpleNamespace(tools={}, prompts=None, resources=None)

        async def list_tools(self, cursor=None):
            return {
                "tools": [{"name": "second" if cursor else "first"}],
                "nextCursor": None if cursor else "page-2",
            }

        async def list_prompts(self):
            raise AssertionError("prompts are not supported")

        async def list_resources(self):
            raise AssertionError("resources are not supported")

    @asynccontextmanager
    async def factory(_config):
        yield ToolsOnlySession()

    async def run():
        manager = DownstreamConnectionManager(session_factory=factory)
        connection = manager.register(
            DownstreamServerConfig(
                name="demo",
                transport=DownstreamTransport.STDIO,
                command="unused",
                reconnect_attempts=0,
            )
        )
        try:
            capabilities = await connection.connect()
            assert [tool.name for tool in capabilities.tools] == ["first", "second"]
            assert capabilities.prompts == []
            assert capabilities.resources == []
        finally:
            await connection.disconnect()

    asyncio.run(run())


@pytest.mark.parametrize(
    "overrides",
    [
        {"transport": "unsupported"},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"reconnect_attempts": -1},
        {"reconnect_backoff_seconds": -1},
    ],
)
def test_invalid_connection_limits_are_rejected(overrides) -> None:
    values = {"name": "demo", "transport": DownstreamTransport.STDIO, "command": "unused"}
    values.update(overrides)
    with pytest.raises(ValueError):
        DownstreamServerConfig(**values).validate()


def test_real_stdio_server_connect_call_and_cleanup(tmp_path) -> None:
    """Exercise SDK task groups and subprocess teardown, not just fake sessions."""
    import sys

    script = tmp_path / "mcp_fixture.py"
    script.write_text(
        "from fastmcp import FastMCP\n"
        "mcp = FastMCP('fixture')\n"
        "@mcp.tool()\n"
        "def echo(value: str) -> str:\n"
        "    return value\n"
        "mcp.run(transport='stdio', show_banner=False)\n"
    )

    async def run():
        manager = DownstreamConnectionManager()
        connection = manager.register(
            DownstreamServerConfig(
                name="fixture",
                transport=DownstreamTransport.STDIO,
                command=sys.executable,
                args=[str(script)],
                reconnect_attempts=0,
            )
        )
        try:
            connected = await manager.connect_all()
            assert connected["fixture"]["state"] == "ready"
            result = await manager.call_tool("fixture", "echo", {"value": "round-trip"})
            assert result.ok
            assert result.content[0].text == "round-trip"
        finally:
            await connection.disconnect()
        assert connection.last_error is None
        assert connection.capabilities is None

    asyncio.run(asyncio.wait_for(run(), timeout=30))


def test_tool_timeout_cancels_request_without_replaying_it() -> None:
    calls = []

    class SlowSession(FakeSession):
        async def call_tool(self, name, arguments):
            calls.append(name)
            await asyncio.Event().wait()

    @asynccontextmanager
    async def factory(_config):
        yield SlowSession()

    async def run():
        manager = DownstreamConnectionManager(session_factory=factory)
        connection = manager.register(
            DownstreamServerConfig(
                name="demo",
                transport=DownstreamTransport.STDIO,
                command="unused",
                timeout_seconds=0.02,
            )
        )
        try:
            with pytest.raises(TimeoutError):
                await manager.call_tool("demo", "slow")
            assert calls == ["slow"]
        finally:
            await connection.disconnect()

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
