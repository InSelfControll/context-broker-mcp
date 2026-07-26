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
from context_broker.router_ttc.tools.safety_tools import (
    SafetyDecision,
    assess_tool_execution,
    redact_secrets,
)


def canonical_json(value: Any) -> str:
    """Serialize a gateway value using the canonical wire representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def canonical_token_count(value: Any, encoder: Any | None = None) -> int:
    """Count tokens in the exact canonical gateway wire representation."""
    active_encoder = encoder or get_encoder()
    return len(active_encoder.encode(canonical_json(value)))


def _candidate_context_items(search_result: dict[str, Any]) -> list[dict[str, str]]:
    """Allowlist and redact search result fields eligible for context trimming."""
    candidate_items: list[dict[str, str]] = []
    raw_results = search_result.get("results", [])
    if not isinstance(raw_results, list):
        return candidate_items

    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            continue
        redacted_result = redact_secrets(raw_result)
        path = redacted_result.get("path", "")
        content = redacted_result.get("content", "")
        safe_path = path if isinstance(path, str) else str(path)
        safe_content = content if isinstance(content, str) else str(content)
        candidate_items.append({"path": safe_path, "content": safe_content})
    return candidate_items


def _handoff_payload(
    task: str,
    route: dict[str, Any],
    items: list[dict[str, str]],
    token_budget: int,
    candidate_tokens: int,
    issuance: dict[str, Any] | None,
    encoder: Any,
) -> dict[str, Any]:
    """Build a handoff and stabilize metrics embedded in its own token count."""
    payload: dict[str, Any] = {
        "version": "ucr.external_handoff.v1",
        "task": task,
        "route": route,
        "context": {
            "items": items,
            "token_count": canonical_token_count(items, encoder),
            "budget": token_budget,
        },
        "metrics": {
            "candidate_tokens": candidate_tokens,
            "sent_tokens": 0,
            "saved_tokens": candidate_tokens,
        },
    }
    if issuance is not None:
        payload["issuance"] = issuance

    for _ in range(32):
        sent_tokens = canonical_token_count(payload, encoder)
        metrics = payload["metrics"]
        updated = {
            "candidate_tokens": candidate_tokens,
            "sent_tokens": sent_tokens,
            "saved_tokens": max(0, candidate_tokens - sent_tokens),
        }
        if metrics == updated:
            return payload
        payload["metrics"] = updated
    raise RuntimeError("gateway payload token metrics did not stabilize")


def _candidate_payload_token_count(
    task: str,
    route: dict[str, Any],
    candidate_items: list[dict[str, str]],
    token_budget: int,
    issuance: dict[str, Any] | None,
    encoder: Any,
) -> int:
    """Find the fixed-point token count for the complete untrimmed handoff."""
    candidate_tokens = 0
    for _ in range(32):
        payload = _handoff_payload(
            task,
            route,
            candidate_items,
            token_budget,
            candidate_tokens,
            issuance,
            encoder,
        )
        updated = canonical_token_count(payload, encoder)
        if updated == candidate_tokens:
            return updated
        candidate_tokens = updated
    raise RuntimeError("gateway candidate token metrics did not stabilize")


def _fit_value(
    value: str,
    *,
    encoder: Any,
    fits: Any,
) -> str:
    """Return the longest token prefix accepted by the complete-envelope predicate."""
    source_tokens = len(encoder.encode(value))
    low = 0
    high = source_tokens
    best = ""
    while low <= high:
        midpoint = (low + high) // 2
        candidate, _, _ = truncate_to_token_limit(value, encoder, midpoint)
        if fits(candidate):
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


def build_external_handoff(
    task: str,
    *,
    route_result: dict[str, Any],
    search_result: dict[str, Any],
    token_budget: int,
    issuance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a secret-safe handoff bounded by its complete canonical payload."""
    if token_budget <= 0:
        raise ValueError("token budget must be positive")
    encoder = get_encoder()
    safe_task = redact_secrets(task)
    route = {
        "intent": redact_secrets(route_result.get("intent", {})),
        "exposure_set": redact_secrets(route_result.get("exposure_set", {})),
        "plan": redact_secrets(route_result.get("plan", {})),
    }
    safe_issuance = redact_secrets(issuance) if issuance is not None else None
    candidate_items = _candidate_context_items(search_result)
    candidate_tokens = _candidate_payload_token_count(
        safe_task,
        route,
        candidate_items,
        token_budget,
        safe_issuance,
        encoder,
    )

    def payload_for(items: list[dict[str, str]]) -> dict[str, Any]:
        return _handoff_payload(
            safe_task,
            route,
            items,
            token_budget,
            candidate_tokens,
            safe_issuance,
            encoder,
        )

    empty_payload = payload_for([])
    if canonical_token_count(empty_payload, encoder) > token_budget:
        raise ValueError("gateway token budget is smaller than mandatory handoff fields")

    items: list[dict[str, str]] = []
    for candidate in candidate_items:
        full_items = [*items, dict(candidate)]
        if canonical_token_count(payload_for(full_items), encoder) <= token_budget:
            items = full_items
            continue

        item = {"path": "", "content": ""}
        if canonical_token_count(payload_for([*items, item]), encoder) > token_budget:
            break
        item["path"] = _fit_value(
            candidate["path"],
            encoder=encoder,
            fits=lambda value: canonical_token_count(
                payload_for([*items, {"path": value, "content": ""}]),
                encoder,
            )
            <= token_budget,
        )
        item["content"] = _fit_value(
            candidate["content"],
            encoder=encoder,
            fits=lambda value: canonical_token_count(
                payload_for([*items, {"path": item["path"], "content": value}]),
                encoder,
            )
            <= token_budget,
        )
        items.append(item)
        break

    handoff = payload_for(items)
    if canonical_token_count(handoff, encoder) > token_budget:
        raise RuntimeError("gateway payload exceeded its canonical token budget")
    return handoff


def prepare_gateway_components(
    task: str,
    project_root: str = "",
    token_budget: int = 1200,
    top_k: int = 5,
    registry: ToolRegistry | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Route and search without issuing authority or constructing a handoff."""
    if not task:
        raise ValueError("task must not be empty")
    if token_budget <= 0:
        raise ValueError("token budget must be positive")

    effective_token_budget = min(token_budget, gateway_token_budget())
    route_kwargs: dict[str, Any] = {
        "mode": "plan_only",
        "token_budget": effective_token_budget,
        "top_k": top_k,
    }
    if registry is not None:
        route_kwargs["registry"] = registry
    route_result = route_task(task, **route_kwargs)
    search_result = (
        search_context(task, project_root=project_root, top_k=top_k)["result"]
        if project_root
        else {"results": [], "context_tokens": 0}
    )
    return route_result, search_result, effective_token_budget


def prepare_gateway_request(
    task: str,
    project_root: str = "",
    token_budget: int = 1200,
    top_k: int = 5,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Prepare a routing-first, bounded context handoff without calling a provider."""
    route_result, search_result, effective_token_budget = prepare_gateway_components(
        task,
        project_root=project_root,
        token_budget=token_budget,
        top_k=top_k,
        registry=registry,
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


def preflight_gateway_plan(
    plan: dict[str, Any],
    arguments_by_tool: dict[str, dict[str, Any]] | None = None,
    registry: ToolRegistry | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Evaluate plan safety without executing local or downstream side effects."""
    active_registry = registry or ToolRegistry()
    arguments_by_tool = arguments_by_tool or {}
    results: list[dict[str, Any]] = []
    for node in plan.get("nodes", []):
        tool_id = str(node.get("tool_id", ""))
        descriptor = active_registry.get(tool_id)
        if descriptor is None:
            results.append({"status": "not_found", "tool_id": tool_id})
            continue
        safety = assess_tool_execution(descriptor, arguments_by_tool.get(tool_id, {}))
        if safety.decision == SafetyDecision.BLOCK:
            status = "blocked"
        elif safety.decision == SafetyDecision.CONFIRM and not confirmed:
            status = "needs_confirmation"
        else:
            status = "approved"
        results.append(
            {
                "status": status,
                "tool_id": tool_id,
                "reason": safety.reason,
                "findings": safety.findings,
            }
        )
    status = "blocked" if any(item["status"] == "blocked" for item in results) else "ok"
    if any(item["status"] == "needs_confirmation" for item in results):
        status = "needs_confirmation"
    return {"version": "ucr.execution_result.v1", "status": status, "results": results}


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


def get_gateway_status(
    downstreams: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the active gateway settings and aggregate handoff metrics."""
    status = {
        "version": "ucr.gateway_status.v1",
        "enabled": gateway_mode_enabled(),
        "default_token_budget": gateway_token_budget(),
        "metrics": METRICS.snapshot(),
    }
    if downstreams is not None:
        status["downstreams"] = downstreams
    return status
