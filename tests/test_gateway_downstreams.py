"""Tests for configured downstream MCP servers in gateway mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastmcp import Client
import pytest

from context_broker.client_ttc.codebase.api import (
    DownstreamConnectionManager,
    DownstreamServerConfig,
)
from context_broker.router_ttc.tools.registry_tools import ToolRegistry
from context_broker.server_ttc.codebase.assembly import create_mcp_server


class FakeDownstreamSession:
    """Realistic MCP session boundary without starting a network service."""

    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self.fail_calls = False

    async def list_tools(self) -> Any:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="lookup",
                    description=f"lookup library documentation {self.secret}",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                )
            ]
        )

    async def list_prompts(self) -> Any:
        return SimpleNamespace(prompts=[])

    async def list_resources(self) -> Any:
        return SimpleNamespace(resources=[])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if self.fail_calls:
            raise RuntimeError(f"downstream failed with {self.secret}")
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text=f"result contains {self.secret}",
                )
            ],
            isError=False,
        )


def _write_downstream_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [
                    {
                        "name": "context7",
                        "transport": "http",
                        "url": "https://mcp.example.test",
                        "headers": {"Authorization": "${CONTEXT7_AUTH}"},
                        "env": {"CONTEXT7_TOKEN": "${CONTEXT7_TOKEN}"},
                        "reconnect_attempts": 0,
                    }
                ],
            }
        )
    )


def _downstream_plan() -> dict[str, Any]:
    return {
        "version": "ucr.plan.v1",
        "nodes": [
            {
                "id": "n1",
                "tool_id": "context7.lookup",
                "server": "context7",
                "risk_level": "medium",
            }
        ],
    }


def test_downstream_config_expands_only_injected_environment_references(
    tmp_path: Path,
) -> None:
    """Reject stored credentials while resolving injected variables for transports."""
    from context_broker.gateway_ttc.tools.downstream_config_tools import (
        load_downstream_server_configs,
    )

    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    configs = load_downstream_server_configs(
        config_path,
        environ={
            "CONTEXT7_AUTH": "opaque-auth-value",
            "CONTEXT7_TOKEN": "opaque-token-value",
        },
    )

    assert len(configs) == 1
    assert configs[0].headers == {"Authorization": "opaque-auth-value"}
    assert configs[0].env == {"CONTEXT7_TOKEN": "opaque-token-value"}
    assert "opaque-auth-value" not in config_path.read_text()
    assert "opaque-token-value" not in config_path.read_text()


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        (
            "downstreams.json",
            {"version": "wrong", "servers": []},
            "ucr.gateway_downstreams.v1",
        ),
        (
            "downstreams.json",
            {"version": "ucr.gateway_downstreams.v1", "servers": {}},
            "servers",
        ),
        (
            ".env",
            {"version": "ucr.gateway_downstreams.v1", "servers": []},
            ".env",
        ),
        (
            "downstreams.json",
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [
                    {
                        "name": "context7",
                        "transport": "http",
                        "url": "https://mcp.example.test",
                        "headers": {"Authorization": "stored-secret-value"},
                    }
                ],
            },
            "environment reference",
        ),
    ],
)
def test_downstream_config_rejects_unsafe_or_invalid_documents(
    tmp_path: Path,
    filename: str,
    payload: dict[str, Any],
    message: str,
) -> None:
    """Fail closed on invalid schema, secret files, and literal credential values."""
    from context_broker.gateway_ttc.tools.downstream_config_tools import (
        load_downstream_server_configs,
    )

    config_path = tmp_path / filename
    config_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=message) as error:
        load_downstream_server_configs(config_path, environ={})

    assert "stored-secret-value" not in str(error.value)


@pytest.mark.anyio
async def test_runtime_discovers_into_combined_registry_and_reports_safe_status(
    tmp_path: Path,
) -> None:
    """Route against discovered tools without exposing resolved credentials."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-runtime-secret"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        try:
            yield session
        finally:
            session.closed = True

    manager = DownstreamConnectionManager(session_factory=fake_factory)
    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=manager,
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )

    handoff = await runtime.prepare_gateway_request(
        "context7 lookup library documentation",
        token_budget=400,
        top_k=1,
    )
    status = runtime.status()
    persisted_registry = (tmp_path / "registry" / "token-slim-router-tools.json").read_text()

    assert runtime.registry.get("search_codebase_tool") is not None
    assert runtime.registry.get("context7.lookup") is not None
    assert handoff["route"]["exposure_set"]["tools"] == ["context7.lookup"]
    assert status["initialization_state"] == "ready"
    assert status["server_count"] == 1
    assert status["ready_count"] == 1
    assert status["tool_count"] == 1
    assert status["servers"] == [
        {
            "name": "context7",
            "state": "ready",
            "tool_count": 1,
            "prompt_count": 0,
            "resource_count": 0,
        }
    ]
    assert secret not in json.dumps(handoff)
    assert secret not in json.dumps(status)
    assert secret not in persisted_registry

    await runtime.close()
    assert session.closed is True


@pytest.mark.anyio
async def test_runtime_requires_confirmation_before_downstream_execution(
    tmp_path: Path,
) -> None:
    """Never call a medium-risk downstream tool until the existing gate approves it."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession("opaque-runtime-secret")

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        yield session

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={
            "CONTEXT7_AUTH": "opaque-runtime-secret",
            "CONTEXT7_TOKEN": "opaque-runtime-secret",
        },
        manager=DownstreamConnectionManager(session_factory=fake_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )

    unconfirmed = await runtime.execute_gateway_plan(
        _downstream_plan(),
        arguments_by_tool={"context7.lookup": {"query": "FastMCP lifespan"}},
    )

    assert unconfirmed["status"] == "needs_confirmation"
    assert unconfirmed["results"][0]["status"] == "needs_confirmation"
    assert session.calls == []

    confirmed = await runtime.execute_gateway_plan(
        _downstream_plan(),
        arguments_by_tool={"context7.lookup": {"query": "FastMCP lifespan"}},
        confirmed=True,
    )

    assert confirmed["status"] == "ok"
    assert confirmed["results"][0]["status"] == "ok"
    assert confirmed["results"][0]["server"] == "context7"
    assert confirmed["results"][0]["result"]["tool"] == "lookup"
    assert session.calls == [("lookup", {"query": "FastMCP lifespan"})]
    assert "opaque-runtime-secret" not in json.dumps(confirmed)

    await runtime.close()


@pytest.mark.anyio
async def test_runtime_redacts_downstream_failures(tmp_path: Path) -> None:
    """Return a safe execution error even when a downstream echoes a resolved secret."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-runtime-secret"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        yield session

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=DownstreamConnectionManager(session_factory=fake_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )
    await runtime.initialize()
    session.fail_calls = True

    result = await runtime.execute_gateway_plan(
        _downstream_plan(),
        arguments_by_tool={"context7.lookup": {"query": "documentation"}},
        confirmed=True,
    )

    assert result["status"] == "error"
    assert result["results"][0]["status"] == "error"
    assert result["results"][0]["error"] == "downstream failed with [REDACTED]"
    assert secret not in json.dumps(result)

    await runtime.close()


@pytest.mark.anyio
async def test_runtime_cleanup_never_logs_resolved_secrets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep transport cleanup failures from logging injected credential values."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-cleanup-secret"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)

    @asynccontextmanager
    async def failing_close_factory(
        _config: DownstreamServerConfig,
    ) -> AsyncIterator[Any]:
        try:
            yield session
        finally:
            raise RuntimeError(f"close echoed {secret}")

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=DownstreamConnectionManager(session_factory=failing_close_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )
    await runtime.initialize()

    await runtime.close()

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.anyio
async def test_fastmcp_gateway_reuses_runtime_and_closes_it_on_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep one lazy manager across public requests and release it with server lifespan."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    secret = "opaque-runtime-secret"
    session = FakeDownstreamSession(secret)
    enters = 0

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        nonlocal enters
        enters += 1
        try:
            yield session
        finally:
            session.closed = True

    monkeypatch.setenv("CONTEXT_BROKER_GATEWAY_MODE", "1")
    monkeypatch.setenv("CONTEXT_BROKER_DOWNSTREAM_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CONTEXT7_AUTH", secret)
    monkeypatch.setenv("CONTEXT7_TOKEN", secret)
    runtime = GatewayDownstreamRuntime(
        manager=DownstreamConnectionManager(session_factory=fake_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )
    server = create_mcp_server(gateway_runtime=runtime)

    async with Client(server) as client:
        assert {tool.name for tool in await client.list_tools()} == {
            "prepare_gateway_request",
            "execute_gateway_plan",
            "get_gateway_status",
        }
        assert enters == 0

        await client.call_tool(
            "prepare_gateway_request",
            {
                "task": f"context7 lookup documentation {secret}",
                "token_budget": 400,
                "top_k": 1,
            },
        )
        status_result = await client.call_tool("get_gateway_status", {})
        status = json.loads(str(status_result.data))

        assert enters == 1
        assert status["downstreams"]["ready_count"] == 1

    assert session.closed is True
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
