"""Build bounded, secret-safe context handoffs for external LLM clients."""

from __future__ import annotations

import json
from typing import Any

from context_broker.config import gateway_mode_enabled, gateway_token_budget
from context_broker.gateway_ttc.tools.state import METRICS
from context_broker.indexer_ttc.tasks.snippet_tasks import truncate_to_token_limit
from context_broker.indexer_ttc.tools.model_tools import get_encoder
from context_broker.router_ttc.codebase.api import execute_plan, route_task, search_context
from context_broker.router_ttc.tools.registry_tools import ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets


def _serialized_context_token_count(items: list[dict[str, str]], encoder: Any) -> int:
    """Return the token cost of the exact serialized context items payload."""
    if not items:
        return 0
    return len(encoder.encode(json.dumps(items)))


def _truncate_item_value_to_budget(
    items: list[dict[str, str]],
    item: dict[str, str],
    key: str,
    value: str,
    token_budget: int,
    encoder: Any,
) -> bool:
    """Set one item value to the longest prefix that keeps the serialized payload bounded."""
    item[key] = ""
    if _serialized_context_token_count([*items, item], encoder) > token_budget:
        return False

    used_tokens = _serialized_context_token_count(items, encoder)
    source_tokens = len(encoder.encode(value))
    token_limit = min(source_tokens, max(0, token_budget - used_tokens))
    truncated_value, truncated_tokens, _ = truncate_to_token_limit(value, encoder, token_limit)
    for limit in range(truncated_tokens, -1, -1):
        fitted_value, _, _ = truncate_to_token_limit(truncated_value, encoder, limit)
        item[key] = fitted_value
        if _serialized_context_token_count([*items, item], encoder) <= token_budget:
            return True
    return False


def _build_bounded_context_items(
    search_result: dict[str, Any],
    token_budget: int,
    encoder: Any,
) -> tuple[list[dict[str, str]], int]:
    """Allowlist, redact, and strictly bound serialized search-result context items."""
    items: list[dict[str, str]] = []
    candidate_items: list[dict[str, str]] = []
    raw_results = search_result.get("results", [])

    if not isinstance(raw_results, list):
        return items, 0

    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            continue
        redacted_result = redact_secrets(raw_result)
        path = redacted_result.get("path", "")
        content = redacted_result.get("content", "")
        safe_path = path if isinstance(path, str) else str(path)
        safe_content = content if isinstance(content, str) else str(content)
        candidate_items.append({"path": safe_path, "content": safe_content})

        item = {"path": "", "content": ""}
        if not _truncate_item_value_to_budget(
            items, item, "path", safe_path, token_budget, encoder
        ):
            continue
        if not _truncate_item_value_to_budget(
            items, item, "content", safe_content, token_budget, encoder
        ):
            continue
        items.append(item)

    candidate_tokens = _serialized_context_token_count(candidate_items, encoder)
    return items, candidate_tokens


def build_external_handoff(
    task: str,
    *,
    route_result: dict[str, Any],
    search_result: dict[str, Any],
    token_budget: int,
) -> dict[str, Any]:
    """Create a secret-safe external handoff with context strictly within its budget."""
    encoder = get_encoder()
    items, candidate_tokens = _build_bounded_context_items(search_result, token_budget, encoder)
    sent_tokens = _serialized_context_token_count(items, encoder)

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

    effective_token_budget = min(token_budget, gateway_token_budget())
    route_result = route_task(
        task,
        mode="plan_only",
        token_budget=effective_token_budget,
        top_k=top_k,
    )
    search_result = (
        search_context(task, project_root=project_root, top_k=top_k)["result"]
        if project_root
        else {"results": [], "context_tokens": 0}
    )
    handoff = build_external_handoff(
        task,
        route_result=route_result,
        search_result=search_result,
        token_budget=effective_token_budget,
    )
    metrics = handoff["metrics"]
    METRICS.record_handoff(metrics["candidate_tokens"], metrics["sent_tokens"])
    return handoff


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
        "metrics": METRICS.snapshot(),
    }
