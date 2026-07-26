"""MCP tool handlers for bounded external gateway handoffs."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Context, FastMCP

from context_broker.gateway_ttc.tasks.gateway_tasks import (
    execute_gateway_plan as execute_gateway_plan_api,
    get_gateway_status as get_gateway_status_api,
    prepare_gateway_request as prepare_gateway_request_api,
)
from context_broker.lifecycle import tracked_activity
from context_broker.server_ttc.tasks.router_tasks import _json_loads_object
from context_broker.server_ttc.tools.helpers import progress
from context_broker.utils import log


def register_gateway_tools(mcp: FastMCP) -> None:
    """Register the restricted three-tool gateway MCP surface."""

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
            log(f"🔐 prepare_gateway_request called: task='{task[:60]}...'")
            result = prepare_gateway_request_api(
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
        arguments_by_tool_json: str = "{}",
        confirmed: bool = False,
        ctx: Context = None,
    ) -> str:
        """Execute a gateway plan through the existing router safety gate."""
        with tracked_activity():
            plan = _json_loads_object(plan_json)
            arguments_by_tool = _json_loads_object(arguments_by_tool_json)
            result = execute_gateway_plan_api(
                plan,
                arguments_by_tool=arguments_by_tool,
                confirmed=confirmed,
            )
            await progress(ctx, f"🔐 Gateway plan execution status: {result.get('status')}")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def get_gateway_status(ctx: Context = None) -> str:
        """Return active gateway settings and aggregate handoff metrics."""
        with tracked_activity():
            result: dict[str, Any] = get_gateway_status_api()
            await progress(ctx, "🔐 Gateway status collected")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
