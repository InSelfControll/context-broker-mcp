"""Tests for configured downstream MCP servers in gateway mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import copy
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


@pytest.fixture(autouse=True)
def _run_worker_seam_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid this sandbox's broken cross-thread event-loop wakeup in functional tests."""
    from context_broker.gateway_ttc.tasks import downstream_tasks

    async def run_sync(function: Any) -> Any:
        return function()

    monkeypatch.setattr(downstream_tasks.to_thread, "run_sync", run_sync)


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
                "capabilities": {
                    "file": False,
                    "network": True,
                    "shell": False,
                    "downstream": True,
                },
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


@pytest.mark.parametrize(
    ("server", "secret"),
    [
        (
            {
                "name": "bad.server",
                "transport": "http",
                "url": "https://mcp.example.test",
            },
            "",
        ),
        (
            {
                "name": "bad\nserver",
                "transport": "http",
                "url": "https://mcp.example.test",
            },
            "",
        ),
        (
            {
                "name": "context7",
                "transport": "http",
                "url": "https://alice:literal-url-secret@mcp.example.test",
            },
            "literal-url-secret",
        ),
        (
            {
                "name": "context7",
                "transport": "http",
                "url": "https://mcp.example.test?api_key=literal-query-secret",
            },
            "literal-query-secret",
        ),
        (
            {
                "name": "context7",
                "transport": "stdio",
                "command": "context7-mcp",
                "args": ["--token=literal-arg-secret"],
            },
            "literal-arg-secret",
        ),
        (
            {
                "name": "context7",
                "transport": "stdio",
                "command": "context7-mcp",
                "args": ["--api-key", "literal-next-arg-secret"],
            },
            "literal-next-arg-secret",
        ),
        (
            {
                "name": "context7",
                "transport": "stdio",
                "command": "context7-mcp",
                "args": ["Bearer literal-bearer-secret"],
            },
            "literal-bearer-secret",
        ),
        (
            {
                "name": "context7",
                "transport": "stdio",
                "command": "context7-mcp",
                "args": ["--header", "X-API-Key: literal-header-secret"],
            },
            "literal-header-secret",
        ),
    ],
)
def test_downstream_config_rejects_noncanonical_identity_and_embedded_credentials(
    tmp_path: Path,
    server: dict[str, Any],
    secret: str,
) -> None:
    """Keep identities unambiguous and credentials out of URL and argv storage."""
    from context_broker.gateway_ttc.tools.downstream_config_tools import (
        load_downstream_server_configs,
    )

    config_path = tmp_path / "downstreams.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [server],
            }
        )
    )

    with pytest.raises(ValueError) as error:
        load_downstream_server_configs(config_path, environ={})

    if secret:
        assert secret not in str(error.value)


def test_downstream_config_allows_safe_url_query_and_stdio_arguments(
    tmp_path: Path,
) -> None:
    """Avoid rejecting ordinary non-credential URL parameters and command flags."""
    from context_broker.gateway_ttc.tools.downstream_config_tools import (
        load_downstream_server_configs,
    )

    http_path = tmp_path / "http.json"
    http_path.write_text(
        json.dumps(
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [
                    {
                        "name": "context7",
                        "transport": "http",
                        "url": "https://mcp.example.test?page=1&filter=open",
                    }
                ],
            }
        )
    )
    stdio_path = tmp_path / "stdio.json"
    stdio_path.write_text(
        json.dumps(
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [
                    {
                        "name": "github",
                        "transport": "stdio",
                        "command": "bunx",
                        "args": ["-y", "@example/mcp", "--port", "3000"],
                    }
                ],
            }
        )
    )

    assert load_downstream_server_configs(http_path, environ={})[0].name == "context7"
    assert load_downstream_server_configs(stdio_path, environ={})[0].name == "github"


def test_downstream_config_rejects_symlink_before_reading_target(tmp_path: Path) -> None:
    """Do not let a safe-looking symlink bypass the .env file-name boundary."""
    from context_broker.gateway_ttc.tools.downstream_config_tools import (
        load_downstream_server_configs,
    )

    target = tmp_path / ".env"
    target.write_text(
        json.dumps({"version": "ucr.gateway_downstreams.v1", "servers": []})
    )
    config_path = tmp_path / "downstreams.json"
    config_path.symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        load_downstream_server_configs(config_path, environ={})


@pytest.mark.parametrize(
    "payload",
    [
        {
            "server": "bad.server",
            "tools": [{"name": "lookup", "input_schema": {}}],
        },
        {
            "server": "context7",
            "tools": [{"name": "bad.tool", "input_schema": {}}],
        },
        {
            "server": "context7",
            "tools": [{"name": "bad\ntool", "input_schema": {}}],
        },
        {
            "server": "context7",
            "tools": [
                {"name": "lookup", "input_schema": {}},
                {"name": "lookup", "input_schema": {}},
            ],
        },
    ],
)
def test_registry_rejects_noncanonical_or_duplicate_downstream_identities(
    tmp_path: Path,
    payload: dict[str, Any],
) -> None:
    """Reject ambiguous downstream identities before mutating the registry."""
    registry = ToolRegistry(cache_dir=tmp_path / "registry")

    with pytest.raises(ValueError, match="canonical|duplicate"):
        registry.ingest_downstream_capabilities(payload)

    assert registry.all() == []


def test_registry_rejects_downstream_collision_with_existing_descriptor(
    tmp_path: Path,
) -> None:
    """Discovery cannot overwrite a descriptor already owned by the registry."""
    from context_broker.router_ttc.tools.registry_tools import ToolDescriptor

    registry = ToolRegistry(cache_dir=tmp_path / "registry")
    existing = ToolDescriptor(id="github.list_issues", name="list_issues")
    registry.register(existing)

    with pytest.raises(ValueError, match="collision"):
        registry.ingest_downstream_capabilities(
            {
                "server": "github",
                "tools": [{"name": "list_issues", "input_schema": {}}],
            }
        )

    assert registry.get("github.list_issues") is existing


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
    assert runtime.manager.get("context7").capabilities is None
    assert runtime.manager.get("context7").last_error is None

    await runtime.close()
    assert session.closed is True


@pytest.mark.anyio
async def test_runtime_redacts_exact_credentials_from_the_whole_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply exact-value redaction after the complete handoff has been assembled."""
    from context_broker.gateway_ttc.tasks import gateway_tasks
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-configured-credential"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        yield session

    def fake_search(_task: str, *, project_root: str, top_k: int) -> dict[str, Any]:
        assert project_root == str(tmp_path)
        assert top_k == 1
        return {
            "result": {
                "results": [{"path": f"src/{secret}.py", "content": f"value={secret}"}],
                "context_tokens": 1,
            }
        }

    monkeypatch.setattr(gateway_tasks, "search_context", fake_search)
    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=DownstreamConnectionManager(session_factory=fake_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )

    handoff = await runtime.prepare_gateway_request(
        f"inspect {secret}",
        project_root=str(tmp_path),
        token_budget=400,
        top_k=1,
    )

    assert secret not in json.dumps(handoff)
    assert "[REDACTED]" in json.dumps(handoff)
    await runtime.close()


@pytest.mark.anyio
async def test_runtime_redacts_credential_keys_without_losing_collision_values(
    tmp_path: Path,
) -> None:
    """Redact mapping keys and preserve entries when two credentials collapse."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    first_secret = "opaque-first-key"
    second_secret = "opaque-second-key"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)

    class SecretKeySession(FakeDownstreamSession):
        async def list_tools(self) -> Any:
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="lookup",
                        description="lookup",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                first_secret: {"type": "string"},
                                second_secret: {"type": "string"},
                            },
                        },
                    )
                ]
            )

        async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
            self.calls.append((name, arguments))
            return SimpleNamespace(
                content={first_secret: "first-value", second_secret: "second-value"},
                isError=False,
            )

    session = SecretKeySession(first_secret)

    @asynccontextmanager
    async def fake_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        yield session

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": first_secret, "CONTEXT7_TOKEN": second_secret},
        manager=DownstreamConnectionManager(session_factory=fake_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )
    await runtime.initialize()

    persisted = (tmp_path / "registry" / "token-slim-router-tools.json").read_text()
    result = await runtime.execute_gateway_plan(
        _downstream_plan(),
        arguments_by_tool={"context7.lookup": {"query": "documentation"}},
        confirmed=True,
    )
    content = result["results"][0]["result"]["content"]

    assert first_secret not in persisted
    assert second_secret not in persisted
    assert first_secret not in json.dumps(result)
    assert second_secret not in json.dumps(result)
    assert sorted(content.values()) == ["first-value", "second-value"]
    assert len(content) == 2
    assert len(set(content)) == 2
    await runtime.close()


@pytest.mark.anyio
async def test_runtime_retries_failed_discovery_on_a_later_request(tmp_path: Path) -> None:
    """A transient first discovery failure must not permanently poison the runtime."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-retry-secret"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)
    attempts = 0

    @asynccontextmanager
    async def flaky_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(f"temporary failure containing {secret}")
        yield session

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=DownstreamConnectionManager(session_factory=flaky_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )

    await runtime.initialize()
    failed_connection = runtime.manager.get("context7")
    assert runtime.status()["initialization_state"] == "degraded"
    assert runtime.registry.get("context7.lookup") is None
    assert failed_connection is not None
    assert failed_connection.last_error is None

    await runtime.initialize()

    assert attempts == 2
    assert runtime.registry.get("context7.lookup") is not None
    assert runtime.status()["initialization_state"] == "ready"
    assert runtime.status()["ready_count"] == 1
    await runtime.close()


@pytest.mark.anyio
async def test_fastmcp_status_request_retries_failed_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later public status request must retry a previously failed server."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-status-retry-secret"
    config_path = tmp_path / "downstreams.json"
    _write_downstream_config(config_path)
    session = FakeDownstreamSession(secret)
    attempts = 0

    @asynccontextmanager
    async def flaky_factory(_config: DownstreamServerConfig) -> AsyncIterator[Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(f"temporary failure containing {secret}")
        yield session

    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"CONTEXT7_AUTH": secret, "CONTEXT7_TOKEN": secret},
        manager=DownstreamConnectionManager(session_factory=flaky_factory),
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )
    monkeypatch.setenv("CONTEXT_BROKER_GATEWAY_MODE", "1")
    server = create_mcp_server(gateway_runtime=runtime)

    async with Client(server) as client:
        first = await client.call_tool("get_gateway_status", {})
        second = await client.call_tool("get_gateway_status", {})

    first_status = json.loads(str(first.data))["downstreams"]
    second_status = json.loads(str(second.data))["downstreams"]
    assert first_status["initialization_state"] == "degraded"
    assert second_status["initialization_state"] == "ready"
    assert attempts == 2
    assert secret not in json.dumps(first_status)
    assert secret not in json.dumps(second_status)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("version", "ucr.plan.v0"),
        ("server", "attacker"),
        ("risk_level", "low"),
        (
            "capabilities",
            {"file": True, "network": False, "shell": False, "downstream": True},
        ),
    ],
)
async def test_runtime_rejects_stale_or_tampered_plan_metadata(
    tmp_path: Path,
    field: str,
    replacement: Any,
) -> None:
    """Bind execution to the supported plan version and live registry descriptor."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-plan-secret"
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
    plan = copy.deepcopy(_downstream_plan())
    if field == "version":
        plan["version"] = replacement
    else:
        plan["nodes"][0][field] = replacement

    result = await runtime.execute_gateway_plan(plan, confirmed=True)

    assert result["version"] == "ucr.execution_result.v1"
    assert result["status"] == "blocked"
    assert result["results"][0]["status"] == "blocked"
    assert session.calls == []
    await runtime.close()


@pytest.mark.anyio
async def test_runtime_failed_initialization_cleans_partial_state_atomically(
    tmp_path: Path,
) -> None:
    """A discovery validation failure must leave no sessions, secrets, or partial tools."""
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime

    secret = "opaque-atomic-secret"
    config_path = tmp_path / "downstreams.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "ucr.gateway_downstreams.v1",
                "servers": [
                    {
                        "name": name,
                        "transport": "http",
                        "url": f"https://{name}.example.test",
                        "headers": {"Authorization": "${DOWNSTREAM_AUTH}"},
                        "reconnect_attempts": 0,
                    }
                    for name in ("alpha", "zeta")
                ],
            }
        )
    )
    sessions: dict[str, FakeDownstreamSession] = {}

    @asynccontextmanager
    async def fake_factory(config: DownstreamServerConfig) -> AsyncIterator[Any]:
        session = FakeDownstreamSession(secret)
        if config.name == "zeta":
            async def invalid_tools() -> Any:
                return SimpleNamespace(
                    tools=[
                        SimpleNamespace(
                            name="bad.tool",
                            description=secret,
                            inputSchema={"type": "object"},
                        )
                    ]
                )

            session.list_tools = invalid_tools  # type: ignore[method-assign]
        sessions[config.name] = session
        try:
            yield session
        finally:
            session.closed = True

    old_manager = DownstreamConnectionManager(session_factory=fake_factory)
    runtime = GatewayDownstreamRuntime(
        config_path=config_path,
        environ={"DOWNSTREAM_AUTH": secret},
        manager=old_manager,
        registry=ToolRegistry(cache_dir=tmp_path / "registry"),
    )

    with pytest.raises(ValueError, match="canonical"):
        await runtime.initialize()

    assert all(session.closed for session in sessions.values())
    assert all(connection.capabilities is None for connection in old_manager.all())
    assert all(connection.last_error is None for connection in old_manager.all())
    assert runtime.manager.all() == []
    assert runtime.registry.get("alpha.lookup") is None
    assert runtime.status()["initialization_state"] == "failed"
    assert runtime.status()["server_count"] == 0
    assert runtime._secret_values == set()
    persisted = (tmp_path / "registry" / "token-slim-router-tools.json").read_text()
    assert secret not in persisted


@pytest.mark.anyio
async def test_runtime_offloads_sync_prepare_and_safety_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not block the event-loop thread with synchronous routing or safety work."""
    from context_broker.gateway_ttc.tasks import downstream_tasks
    from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime
    from context_broker.router_ttc.tools.registry_tools import ToolDescriptor

    registry = ToolRegistry(cache_dir=tmp_path / "registry")
    descriptor = ToolDescriptor(
        id="inspect",
        name="inspect",
        server="context-broker",
        risk_level="low",
        capabilities={"file": False, "network": False, "shell": False},
    )
    registry.register(descriptor)
    offloaded_functions: list[Any] = []

    def fake_prepare(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"version": "ucr.external_handoff.v1"}

    def fake_execute(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"version": "ucr.execution_result.v1", "status": "ok", "results": []}

    async def fake_run_sync(function: Any) -> Any:
        offloaded_functions.append(function)
        return function()

    monkeypatch.setattr(downstream_tasks, "prepare_gateway_request_api", fake_prepare)
    monkeypatch.setattr(downstream_tasks, "execute_gateway_plan_api", fake_execute)
    monkeypatch.setattr(downstream_tasks.to_thread, "run_sync", fake_run_sync)
    runtime = GatewayDownstreamRuntime(registry=registry)
    plan = {
        "version": "ucr.plan.v1",
        "nodes": [
            {
                "id": "n1",
                "tool_id": "inspect",
                "server": descriptor.server,
                "risk_level": descriptor.risk_level,
                "capabilities": descriptor.capabilities,
            }
        ],
    }

    await runtime.prepare_gateway_request("inspect")
    await runtime.execute_gateway_plan(plan)

    assert len(offloaded_functions) == 2
    assert all(callable(function) for function in offloaded_functions)
    await runtime.close()


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
