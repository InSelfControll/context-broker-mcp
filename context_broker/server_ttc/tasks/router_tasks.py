"""MCP tool handlers for the Universal Context Router."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Context, FastMCP

from context_broker.lifecycle import tracked_activity
from context_broker.router_ttc.codebase.api import (
    benchmark_route_task as benchmark_route_task_api,
    execute_plan as execute_plan_api,
    execute_selected_tool as execute_selected_tool_api,
    explain_plan as explain_plan_api,
    get_route_metrics as get_route_metrics_api,
    route_task as route_task_api,
    search_context as search_context_api,
)
from context_broker.server_ttc.tools.helpers import progress
from context_broker.utils import log


def _json_loads_object(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must decode to an object")
    return payload


def register_router_tools(mcp: FastMCP) -> None:
    """Register UCR public tools plus backward-compatible execution helper."""

    @mcp.tool()
    async def route_task(
        task: str,
        mode: str = "recommend_tools",
        token_budget: int = 1200,
        top_k: int = 8,
        ctx: Context = None,
    ) -> str:
        """Route a task to the smallest relevant MCP tool slice."""
        with tracked_activity():
            log(f"🧭 route_task called: mode={mode}, task='{task[:60]}...'")
            result = route_task_api(task, mode=mode, token_budget=token_budget, top_k=top_k)
            report = result["token_report"]
            await progress(
                ctx,
                (
                    "🧭 Router selected "
                    f"{report['exposed_tools']}/{report['total_tools']} tools; "
                    f"saved {report['saved_percent']:.1f}% tool tokens"
                ),
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def execute_plan(
        plan_json: str,
        arguments_by_tool_json: str = "{}",
        confirmed: bool = False,
        ctx: Context = None,
    ) -> str:
        """Execute a UCR plan through safety gates, delegating downstream calls as needed."""
        with tracked_activity():
            plan = _json_loads_object(plan_json)
            arguments_by_tool = _json_loads_object(arguments_by_tool_json)
            result = execute_plan_api(plan, arguments_by_tool=arguments_by_tool, confirmed=confirmed)
            await progress(ctx, f"🧭 Plan execution status: {result.get('status')}")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def search_context(query: str, project_root: str = "", top_k: int = 5, ctx: Context = None) -> str:
        """Search relevant project context through the UCR public surface."""
        with tracked_activity():
            result = search_context_api(query, project_root=project_root, top_k=top_k)
            await progress(ctx, "🔎 search_context completed")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def explain_plan(plan_json: str, ctx: Context = None) -> str:
        """Explain a UCR plan in client-neutral JSON."""
        with tracked_activity():
            result = explain_plan_api(_json_loads_object(plan_json))
            await progress(ctx, "📋 Plan explanation generated")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def execute_selected_tool(
        tool_id: str,
        arguments_json: str = "{}",
        confirmed: bool = False,
        ctx: Context = None,
    ) -> str:
        """Backward-compatible helper: run one selected tool through the safety gate."""
        with tracked_activity():
            log(f"🛡️ execute_selected_tool called: tool_id={tool_id}")
            arguments = _json_loads_object(arguments_json)
            result = execute_selected_tool_api(tool_id, arguments, confirmed=confirmed)
            await progress(ctx, f"🛡️ Router execution status: {result.get('status')}")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def get_route_metrics(ctx: Context = None) -> str:
        """Return UCR route/execution metrics for observability dashboards."""
        with tracked_activity():
            result = get_route_metrics_api()
            await progress(ctx, "📈 Route metrics collected")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def benchmark_router(iterations: int = 20, ctx: Context = None) -> str:
        """Run a lightweight in-process router benchmark."""
        with tracked_activity():
            result = benchmark_route_task_api(iterations=iterations)
            await progress(ctx, "🏁 Router benchmark completed")
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
