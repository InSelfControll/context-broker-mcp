"""MCP tool handlers for bounded external gateway handoffs."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
import json
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan

from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime
from context_broker.gateway_ttc.tasks.gateway_tasks import get_gateway_status as get_gateway_status_api
from context_broker.lifecycle import tracked_activity
from context_broker.server_ttc.tasks.router_tasks import _json_loads_object
from context_broker.server_ttc.tools.helpers import progress
from context_broker.utils import log


def create_gateway_lifespan(
    runtime: GatewayDownstreamRuntime,
) -> Callable[[FastMCP], Lifespan]:
    """Create a FastMCP lifespan that closes the persistent downstream runtime."""

    @lifespan
    async def gateway_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {"gateway_runtime": runtime}
        finally:
            await runtime.close()

    return gateway_lifespan


def register_gateway_tools(
    mcp: FastMCP,
    runtime: GatewayDownstreamRuntime | None = None,
) -> None:
    """Register the restricted three-tool gateway MCP surface."""
    active_runtime = runtime or GatewayDownstreamRuntime()

    @mcp.tool()
    async def prepare_gateway_request(
        task: str,
        project_root: str = "",
        token_budget: int = 1200,
        top_k: int = 5,
        ctx: Context = None,
    ) -> str:
        """Prepare a bounded, secret-safe context handoff for an external client."""
        with tracked_activity():
            log("🔐 prepare_gateway_request called")
            result = await active_runtime.prepare_gateway_request(
                task,
                project_root=project_root,
                token_budget=token_budget,
                top_k=top_k,
            )
            await progress(ctx, "🔐 Gateway request prepared")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def execute_gateway_plan(
        plan_json: str,
        issuance_claim: str,
        arguments_by_tool_json: str = "{}",
        confirmed: bool = False,
        ctx: Context = None,
    ) -> str:
        """Execute a gateway plan through the existing router safety gate."""
        with tracked_activity():
            plan = _json_loads_object(plan_json)
            arguments_by_tool = _json_loads_object(arguments_by_tool_json)
            result = await active_runtime.execute_gateway_plan(
                plan,
                issuance_claim,
                arguments_by_tool=arguments_by_tool,
                confirmed=confirmed,
            )
            await progress(ctx, f"🔐 Gateway plan execution status: {result.get('status')}")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def get_gateway_status(ctx: Context = None) -> str:
        """Return active gateway settings and aggregate handoff metrics."""
        with tracked_activity():
            try:
                await active_runtime.initialize()
            except Exception:
                pass
            result: dict[str, Any] = get_gateway_status_api(active_runtime.status())
            await progress(ctx, "🔐 Gateway status collected")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
