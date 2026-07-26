"""Persistent downstream MCP runtime for credential-preserving gateway mode."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import hashlib
from pathlib import Path
import secrets
import time
from typing import Any, Mapping

from anyio import to_thread

from context_broker.client_ttc.codebase.api import (
    ConnectionState,
    DownstreamConnectionManager,
    ManagedDownstreamConnection,
)
from context_broker.config import (
    CACHE_DIR,
    gateway_downstream_config_path,
    gateway_plan_claim_ttl_seconds,
)
from context_broker.gateway_ttc.tasks.gateway_tasks import (
    build_external_handoff,
    canonical_json,
    execute_gateway_plan as execute_gateway_plan_api,
    preflight_gateway_plan,
    prepare_gateway_components,
)
from context_broker.gateway_ttc.tools.downstream_config_tools import (
    load_downstream_server_configs,
)
from context_broker.gateway_ttc.tools.state import METRICS
from context_broker.router_ttc.tools.default_tools import default_tool_descriptors
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor, ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets


@dataclass
class _IssuedPlanClaim:
    """Process-local authority bound to one exact prepared handoff."""

    plan_digest: str
    exposure_set_digest: str
    registry_fingerprint: str
    registry_generation: int
    expires_at: float
    consumed: bool = False


class GatewayDownstreamRuntime:
    """Own one lazy registry and connection manager for the gateway server lifespan."""

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        manager: DownstreamConnectionManager | None = None,
        registry: ToolRegistry | None = None,
        clock: Callable[[], float] = time.time,
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
        self._claim_lock = asyncio.Lock()
        self._clock = clock
        raw_ttl = (
            environ.get("CONTEXT_BROKER_GATEWAY_PLAN_CLAIM_TTL_SECONDS")
            if environ is not None
            else None
        )
        try:
            self._claim_ttl_seconds = max(1, int(raw_ttl)) if raw_ttl else (
                gateway_plan_claim_ttl_seconds()
            )
        except ValueError:
            self._claim_ttl_seconds = gateway_plan_claim_ttl_seconds()
        self._issued_claims: dict[str, _IssuedPlanClaim] = {}
        self._initialized = False
        self._initialization_state = "not_initialized"
        self._secret_values: set[str] = set()
        self._capability_counts: dict[str, dict[str, int]] = {}
        self._baseline_descriptors = tuple(self.registry.all())

    def _redact(self, value: Any) -> Any:
        """Redact generic secret patterns and exact resolved config values."""
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for raw_key, item in value.items():
                base_key = self._redact_text(str(raw_key))
                safe_key = base_key
                suffix = 2
                while safe_key in redacted:
                    safe_key = f"{base_key}#{suffix}"
                    suffix += 1
                redacted[safe_key] = self._redact(item)
            return redacted
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

        return self._redact_text(value)

    def _redact_text(self, value: str) -> str:
        """Redact exact configured credentials and generic patterns from text."""
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

    def _reset_registry_to_baseline(self) -> None:
        """Replace a partially mutated registry with its pre-runtime descriptors."""
        self.registry = ToolRegistry(
            cache_dir=self.registry.cache_dir,
            redis_url=self.registry.redis_url,
        )
        if self._baseline_descriptors:
            self.registry.register_many(self._baseline_descriptors)
        self._register_defaults()

    def _needs_discovery_retry(self) -> bool:
        """Return whether any configured connection is not currently usable."""
        return any(
            connection.state != ConnectionState.READY
            for connection in self.manager.all()
        )

    def _discard_connection_discovery(self, connection: ManagedDownstreamConnection) -> None:
        """Discard raw discovery and exception text after deriving safe state."""
        connection.capabilities = None
        connection.last_error = None

    def _ingest_connection_capabilities(
        self,
        connection: ManagedDownstreamConnection,
        *,
        allow_identical: bool = False,
    ) -> None:
        """Persist a redacted descriptor subset, then discard the raw discovery payload."""
        capabilities = connection.capabilities
        if capabilities is None:
            self._discard_connection_discovery(connection)
            self._capability_counts.setdefault(
                connection.config.name,
                {"tools": 0, "prompts": 0, "resources": 0},
            )
            return

        self._capability_counts[connection.config.name] = {
            "tools": len(capabilities.tools),
            "prompts": len(capabilities.prompts),
            "resources": len(capabilities.resources),
        }
        try:
            safe_capabilities = self._redact(capabilities.to_dict())
            self.registry.ingest_downstream_capabilities(
                safe_capabilities,
                allow_identical=allow_identical,
            )
        finally:
            self._discard_connection_discovery(connection)

    def _refresh_initialization_state(self) -> None:
        """Derive the public state from current connection lifecycle states."""
        self._initialization_state = (
            "degraded" if self._needs_discovery_retry() else "ready"
        )

    async def _retry_failed_connections(self) -> None:
        """Retry only failed connections, preserving established sessions."""
        for connection in self.manager.all():
            if connection.state == ConnectionState.READY:
                continue
            try:
                await connection.connect()
            except Exception:
                self._discard_connection_discovery(connection)
                continue
            self._ingest_connection_capabilities(connection, allow_identical=True)
        self._refresh_initialization_state()

    async def _clean_failed_initialization(self) -> None:
        """Atomically remove partial connections, credentials, and registry entries."""
        failed_manager = self.manager
        session_factory = failed_manager.session_factory
        await asyncio.gather(
            *(connection.disconnect() for connection in failed_manager.all()),
            return_exceptions=True,
        )
        for connection in failed_manager.all():
            self._discard_connection_discovery(connection)
        self.manager = DownstreamConnectionManager(session_factory=session_factory)
        self._capability_counts.clear()
        self._secret_values.clear()
        self.environ = None
        self._initialized = False
        self._reset_registry_to_baseline()
        self._initialization_state = "failed"

    async def initialize(self) -> None:
        """Load once and retry transient discovery failures on later requests."""
        if self._initialized and not self._needs_discovery_retry():
            return
        async with self._lock:
            if self._initialized and not self._needs_discovery_retry():
                return
            if self._initialized:
                self._initialization_state = "initializing"
                try:
                    await self._retry_failed_connections()
                except Exception:
                    await self._clean_failed_initialization()
                    raise
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
                self.environ = None
                for config in configs:
                    self.manager.register(config)

                self._register_defaults()
                await self.manager.discover_all()
                for connection in self.manager.all():
                    self._ingest_connection_capabilities(connection)

                self._refresh_initialization_state()
                self._initialized = True
            except Exception:
                await self._clean_failed_initialization()
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
        safe_task = self._redact_text(task)
        safe_project_root = self._redact_text(project_root)
        route_result, search_result, effective_budget = await to_thread.run_sync(
            partial(
                prepare_gateway_components,
                safe_task,
                project_root=safe_project_root,
                token_budget=token_budget,
                top_k=top_k,
                registry=self.registry,
            )
        )
        claim = secrets.token_urlsafe(32)
        expires_at = self._clock() + self._claim_ttl_seconds
        issuance = {"claim": claim, "expires_at": int(expires_at)}
        handoff = await to_thread.run_sync(
            partial(
                build_external_handoff,
                safe_task,
                route_result=route_result,
                search_result=search_result,
                token_budget=effective_budget,
                issuance=issuance,
            )
        )
        safe_handoff = self._redact(handoff)
        plan = safe_handoff["route"]["plan"]
        exposure_set = safe_handoff["route"]["exposure_set"]
        record = _IssuedPlanClaim(
            plan_digest=self._digest(plan),
            exposure_set_digest=self._digest(exposure_set),
            registry_fingerprint=self.registry.fingerprint(),
            registry_generation=self.registry.generation,
            expires_at=expires_at,
        )
        async with self._claim_lock:
            self._prune_expired_claims()
            self._issued_claims[claim] = record
        metrics = safe_handoff["metrics"]
        METRICS.record_handoff(metrics["candidate_tokens"], metrics["sent_tokens"])
        return safe_handoff

    def _digest(self, value: Any) -> str:
        """Return a stable digest for one claim-bound handoff field."""
        return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

    def _prune_expired_claims(self) -> None:
        """Discard expired authority without exposing claim contents."""
        now = self._clock()
        expired = [
            claim
            for claim, record in self._issued_claims.items()
            if record.expires_at <= now
        ]
        for claim in expired:
            self._issued_claims.pop(claim, None)

    def _claim_error(
        self,
        plan: dict[str, Any],
        issuance_claim: str,
    ) -> str | None:
        """Validate a claim while the claim lock is held."""
        self._prune_expired_claims()
        record = self._issued_claims.get(issuance_claim)
        if record is None:
            return "gateway plan claim is missing, unknown, or expired"
        if record.consumed:
            return "gateway plan claim has already been consumed"
        if record.plan_digest != self._digest(plan):
            return "gateway plan does not match its issued claim"
        if (
            record.registry_generation != self.registry.generation
            or record.registry_fingerprint != self.registry.fingerprint()
        ):
            return "gateway plan claim is stale after registry drift"
        return None

    def _expected_capabilities(self, descriptor: ToolDescriptor) -> dict[str, Any]:
        """Return the exact planner metadata bound to a live descriptor."""
        return descriptor.capabilities or {
            "file": descriptor.file_capable,
            "network": descriptor.network_capable,
            "shell": descriptor.shell_capable,
        }

    def _plan_binding_error(self, plan: dict[str, Any]) -> str | None:
        """Validate plan version and bind each node to current registry metadata."""
        if plan.get("version") != "ucr.plan.v1":
            return "unsupported or missing gateway plan version"
        nodes = plan.get("nodes")
        if not isinstance(nodes, list):
            return "gateway plan nodes must be an array"

        node_ids: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                return "gateway plan nodes must be objects"
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id or node_id in node_ids:
                return "gateway plan node identities must be non-empty and unique"
            node_ids.add(node_id)
            tool_id = node.get("tool_id")
            if not isinstance(tool_id, str):
                return "gateway plan tool identity is invalid"
            descriptor = self.registry.get(tool_id)
            if descriptor is None:
                return "gateway plan is not bound to a live tool descriptor"
            if (
                node.get("server") != descriptor.server
                or node.get("risk_level") != descriptor.risk_level
                or node.get("capabilities") != self._expected_capabilities(descriptor)
            ):
                return "gateway plan metadata does not match the live tool descriptor"
        return None

    def _blocked_execution(self, reason: str) -> dict[str, Any]:
        """Return the public execution schema for a rejected plan."""
        return {
            "version": "ucr.execution_result.v1",
            "status": "blocked",
            "results": [{"status": "blocked", "reason": reason}],
        }

    async def execute_gateway_plan(
        self,
        plan: dict[str, Any],
        issuance_claim: str,
        arguments_by_tool: dict[str, dict[str, Any]] | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Validate issued authority, then execute approved delegations at most once."""
        async with self._claim_lock:
            claim_error = self._claim_error(plan, issuance_claim)
        if claim_error is not None:
            return self._redact(self._blocked_execution(claim_error))

        await self.initialize()
        arguments_by_tool = arguments_by_tool or {}
        binding_error = self._plan_binding_error(plan)
        if binding_error is not None:
            return self._redact(self._blocked_execution(binding_error))
        preflight = await to_thread.run_sync(
            partial(
                preflight_gateway_plan,
                plan,
                arguments_by_tool=arguments_by_tool,
                registry=self.registry,
                confirmed=confirmed,
            )
        )
        if preflight["status"] in {"blocked", "needs_confirmation"}:
            return self._redact(preflight)

        async with self._claim_lock:
            claim_error = self._claim_error(plan, issuance_claim)
            if claim_error is not None:
                return self._redact(self._blocked_execution(claim_error))
            self._issued_claims[issuance_claim].consumed = True

        execution = await to_thread.run_sync(
            partial(
                execute_gateway_plan_api,
                plan,
                arguments_by_tool=arguments_by_tool,
                registry=self.registry,
                confirmed=confirmed,
            )
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
                    self._refresh_initialization_state()
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
            counts = self._capability_counts.get(
                connection.config.name,
                {"tools": 0, "prompts": 0, "resources": 0},
            )
            servers.append(
                {
                    "name": connection.config.name,
                    "state": connection.state.value,
                    "tool_count": counts["tools"],
                    "prompt_count": counts["prompts"],
                    "resource_count": counts["resources"],
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
            for connection in self.manager.all():
                self._discard_connection_discovery(connection)
            self.manager = DownstreamConnectionManager(session_factory=session_factory)
            self._capability_counts.clear()
            self._secret_values.clear()
            self.environ = None
            async with self._claim_lock:
                self._issued_claims.clear()
            self._initialized = False
            self._reset_registry_to_baseline()
            self._initialization_state = "closed"
