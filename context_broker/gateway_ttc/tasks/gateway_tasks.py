"""Build bounded, secret-safe context handoffs for external LLM clients."""

from __future__ import annotations

from typing import Any

from context_broker.config import gateway_mode_enabled, gateway_token_budget
from context_broker.gateway_ttc.tools.state import METRICS
from context_broker.indexer_ttc.tasks.snippet_tasks import truncate_to_token_limit
from context_broker.indexer_ttc.tools.model_tools import get_encoder
from context_broker.router_ttc.codebase.api import execute_plan, route_task, search_context
from context_broker.router_ttc.tools.registry_tools import ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets


def build_external_handoff(
    task: str,
    *,
    route_result: dict[str, Any],
    search_result: dict[str, Any],
    token_budget: int,
) -> dict[str, Any]:
    """Create a secret-safe external handoff with context strictly within its budget."""
    encoder = get_encoder()
    remaining_tokens = token_budget
    candidate_tokens = 0
    sent_tokens = 0
    items: list[dict[str, Any]] = []
    raw_results = search_result.get("results", [])

    if isinstance(raw_results, list):
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue
            result = redact_secrets(raw_result)
            content = result.get("content", "")
            content = content if isinstance(content, str) else str(content)
            result["content"] = content
            candidate_tokens += len(encoder.encode(content))
            if remaining_tokens <= 0:
                continue
            truncated_content, token_count, _ = truncate_to_token_limit(
                content,
                encoder,
                remaining_tokens,
            )
            result["content"] = truncated_content
            items.append(result)
            sent_tokens += token_count
            remaining_tokens -= token_count

    route = {
        "intent": redact_secrets(route_result.get("intent", {})),
        "exposure_set": redact_secrets(route_result.get("exposure_set", {})),
        "plan": redact_secrets(route_result.get("plan", {})),
    }
    return {
        "version": "ucr.external_handoff.v1",
        "task": redact_secrets(task),
        "route": route,
        "context": {
            "items": items,
            "token_count": sent_tokens,
            "budget": token_budget,
        },
        "metrics": {
            "candidate_tokens": candidate_tokens,
            "sent_tokens": sent_tokens,
            "saved_tokens": max(0, candidate_tokens - sent_tokens),
        },
    }


def prepare_gateway_request(
    task: str,
    project_root: str = "",
    token_budget: int = 1200,
    top_k: int = 5,
) -> dict[str, Any]:
    """Prepare a routing-first, bounded context handoff without calling a provider."""
    if not task:
        raise ValueError("task must not be empty")
    if token_budget <= 0:
        raise ValueError("token budget must be positive")

    route_result = route_task(task, mode="plan_only", token_budget=token_budget, top_k=top_k)
    search_result = (
        search_context(task, project_root=project_root, top_k=top_k)["result"]
        if project_root
        else {"results": [], "context_tokens": 0}
    )
    return build_external_handoff(
        task,
        route_result=route_result,
        search_result=search_result,
        token_budget=token_budget,
    )


def execute_gateway_plan(
    plan: dict[str, Any],
    arguments_by_tool: dict[str, dict[str, Any]] | None = None,
    registry: ToolRegistry | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Execute an already-selected plan through the existing router safety gate."""
    return execute_plan(
        plan,
        arguments_by_tool=arguments_by_tool,
        registry=registry,
        confirmed=confirmed,
    )


def get_gateway_status() -> dict[str, Any]:
    """Return the active gateway settings and aggregate handoff metrics."""
    return {
        "version": "ucr.gateway_status.v1",
        "enabled": gateway_mode_enabled(),
        "default_token_budget": gateway_token_budget(),
        "metrics": {
            "prepared_requests": METRICS.prepared_requests,
            "candidate_tokens": METRICS.candidate_tokens,
            "sent_tokens": METRICS.sent_tokens,
            "saved_tokens": METRICS.saved_tokens,
        },
    }
