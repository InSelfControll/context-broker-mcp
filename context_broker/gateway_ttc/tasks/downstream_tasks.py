"""Persistent downstream MCP runtime for credential-preserving gateway mode."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

from context_broker.client_ttc.codebase.api import DownstreamConnectionManager
from context_broker.config import CACHE_DIR, gateway_downstream_config_path
from context_broker.gateway_ttc.tasks.gateway_tasks import (
    execute_gateway_plan as execute_gateway_plan_api,
)
from context_broker.gateway_ttc.tasks.gateway_tasks import (
    prepare_gateway_request as prepare_gateway_request_api,
)
from context_broker.gateway_ttc.tools.downstream_config_tools import (
    load_downstream_server_configs,
)
from context_broker.router_ttc.tools.default_tools import default_tool_descriptors
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor, ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets


class GatewayDownstreamRuntime:
    """Own one lazy registry and connection manager for the gateway server lifespan."""

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        manager: DownstreamConnectionManager | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        configured_path = (
            str(config_path)
            if config_path is not None
            else gateway_downstream_config_path()
        )
        self.config_path = Path(configured_path) if configured_path else None
        self.environ = environ
        self.manager = manager or DownstreamConnectionManager()
        self.registry = registry or ToolRegistry(cache_dir=Path(CACHE_DIR) / "gateway")
        self._lock = asyncio.Lock()
        self._initialized = False
        self._initialization_state = "not_initialized"
        self._secret_values: set[str] = set()

    def _redact(self, value: Any) -> Any:
        """Redact generic secret patterns and exact resolved config values."""
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._redact(item) for item in value)
        if value is None or isinstance(value, bool | int | float):
            return value
        if not isinstance(value, str):
            model_dump = getattr(value, "model_dump", None)
            if callable(model_dump):
                return self._redact(model_dump())
            if hasattr(value, "__dict__"):
                return self._redact(vars(value))
            return self._redact(str(value))

        redacted = value
        for secret in sorted(self._secret_values, key=len, reverse=True):
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redact_secrets(redacted)

    def _register_defaults(self) -> None:
        existing_ids = {descriptor.id for descriptor in self.registry.all()}
        missing = [
            descriptor
            for descriptor in default_tool_descriptors()
            if descriptor.id not in existing_ids
        ]
        if missing:
            self.registry.register_many(missing)

    async def initialize(self) -> None:
        """Load config and discover capabilities once on the first gateway request."""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            self._initialization_state = "initializing"
            try:
                configs = (
                    load_downstream_server_configs(
                        self.config_path,
                        environ=self.environ,
                    )
                    if self.config_path is not None
                    else []
                )
                self._secret_values = {
                    value
                    for config in configs
                    for value in [*config.env.values(), *config.headers.values()]
                    if value
                }
                for config in configs:
                    self.manager.register(config)

                self._register_defaults()
                await self.manager.discover_all()
                for connection in self.manager.all():
                    if connection.capabilities is None:
                        continue
                    safe_capabilities = self._redact(connection.capabilities.to_dict())
                    self.registry.ingest_downstream_capabilities(safe_capabilities)

                states = [connection.state.value for connection in self.manager.all()]
                self._initialization_state = (
                    "degraded"
                    if any(state != "ready" for state in states)
                    else "ready"
                )
                self._initialized = True
            except Exception:
                await asyncio.gather(
                    *(connection.disconnect() for connection in self.manager.all()),
                    return_exceptions=True,
                )
                self._initialization_state = "failed"
                raise

    async def prepare_gateway_request(
        self,
        task: str,
        project_root: str = "",
        token_budget: int = 1200,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Prepare a handoff routed against built-in and discovered downstream tools."""
        await self.initialize()
        return prepare_gateway_request_api(
            task,
            project_root=project_root,
            token_budget=token_budget,
            top_k=top_k,
            registry=self.registry,
        )

    async def execute_gateway_plan(
        self,
        plan: dict[str, Any],
        arguments_by_tool: dict[str, dict[str, Any]] | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Run the safety gate, then execute only approved downstream delegations."""
        await self.initialize()
        arguments_by_tool = arguments_by_tool or {}
        execution = execute_gateway_plan_api(
            plan,
            arguments_by_tool=arguments_by_tool,
            registry=self.registry,
            confirmed=confirmed,
        )

        results: list[dict[str, Any]] = []
        downstream_error = False
        for raw_result in execution.get("results", []):
            result = dict(raw_result)
            descriptor = self.registry.get(str(result.get("tool_id", "")))
            if self._is_managed_downstream_delegation(result, descriptor):
                assert descriptor is not None
                try:
                    call_result = await self.manager.call_tool(
                        descriptor.server,
                        descriptor.name,
                        arguments_by_tool.get(descriptor.id, {}),
                    )
                    result = {
                        "status": "ok" if call_result.ok else "error",
                        "tool_id": descriptor.id,
                        "server": descriptor.server,
                        "result": self._redact(call_result.to_dict()),
                    }
                    downstream_error = downstream_error or not call_result.ok
                except Exception as exc:
                    downstream_error = True
                    result = {
                        "status": "error",
                        "tool_id": descriptor.id,
                        "server": descriptor.server,
                        "error": self._redact(str(exc)),
                    }
            results.append(self._redact(result))

        safe_execution = dict(execution)
        safe_execution["results"] = results
        if downstream_error:
            safe_execution["status"] = "error"
        return self._redact(safe_execution)

    def _is_managed_downstream_delegation(
        self,
        result: dict[str, Any],
        descriptor: ToolDescriptor | None,
    ) -> bool:
        return bool(
            result.get("status") == "delegated"
            and descriptor is not None
            and descriptor.capabilities.get("downstream") is True
            and self.manager.get(descriptor.server) is not None
        )

    def status(self) -> dict[str, Any]:
        """Return only secret-free server identities, states, and counts."""
        servers = []
        for connection in self.manager.all():
            capabilities = connection.capabilities
            servers.append(
                {
                    "name": connection.config.name,
                    "state": connection.state.value,
                    "tool_count": len(capabilities.tools) if capabilities else 0,
                    "prompt_count": len(capabilities.prompts) if capabilities else 0,
                    "resource_count": len(capabilities.resources) if capabilities else 0,
                }
            )
        return {
            "configured": self.config_path is not None,
            "initialization_state": self._initialization_state,
            "server_count": len(servers),
            "ready_count": sum(server["state"] == "ready" for server in servers),
            "failed_count": sum(server["state"] == "failed" for server in servers),
            "tool_count": sum(int(server["tool_count"]) for server in servers),
            "servers": servers,
        }

    async def close(self) -> None:
        """Disconnect all managed sessions during FastMCP lifespan teardown."""
        async with self._lock:
            session_factory = self.manager.session_factory
            await asyncio.gather(
                *(connection.disconnect() for connection in self.manager.all()),
                return_exceptions=True,
            )
            self.manager = DownstreamConnectionManager(session_factory=session_factory)
            self._secret_values.clear()
            self.environ = None
            self._initialized = False
            self._initialization_state = "closed"
