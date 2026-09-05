"""Routing, planning, safe execution, and observability tasks for UCR."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import perf_counter
from typing import Any, Callable

from context_broker.config import ROUTER_PLAN_CACHE_MAX_ENTRIES
from context_broker.indexer import literal_search, search_codebase
from context_broker.project import resolve_project_root
from context_broker.router_ttc.tasks.planner_tasks import build_plan
from context_broker.router_ttc.tools.default_tools import default_tool_descriptors
from context_broker.router_ttc.tools.observability_tools import benchmark_summary, get_router_metrics
from context_broker.router_ttc.tools.registry_tools import RankedTool, ToolDescriptor, ToolRegistry
from context_broker.router_ttc.tools.safety_tools import (
    SafetyDecision,
    assess_tool_execution,
    redact_secrets,
)
from context_broker.router_ttc.tools.token_tools import descriptor_token_count, token_report_for_selection

RouterMode = str
_PLAN_CACHE: OrderedDict[tuple[str, str, int, int, str], dict[str, Any]] = OrderedDict()
_PLAN_CACHE_LOCK = Lock()


def get_default_registry() -> ToolRegistry:
    """Load or create the default tool registry."""
    registry = ToolRegistry()
    if not registry.load_cache():
        registry.register_many(default_tool_descriptors())
    if not registry.all():
        registry.register_many(default_tool_descriptors())
    return registry


def detect_intent(task: str) -> dict[str, Any]:
    """Detect coarse routing intent from a user task."""
    lowered = task.lower()
    intents = []
    if any(word in lowered for word in ["find", "search", "where", "inspect", "locate"]):
        intents.append("search_context")
    if any(word in lowered for word in ["test", "lint", "benchmark", "perf"]):
        intents.append("verify")
    if any(word in lowered for word in ["write", "save", "create", "update", "generate"]):
        intents.append("mutate")
    if any(word in lowered for word in ["deploy", "shell", "command", "run"]):
        intents.append("execute")
    # Detect literal/exact search intent — queries that name a specific symbol,
    # identifier, or ask for exact text. These should use find_in_codebase
    # (local grep) instead of semantic search to avoid external LLM round-trips.
    _LITERAL_SIGNALS = (
        "session id",
        "session_id",
        "auth function",
        "function def",
        "def ",
        "class ",
        "import ",
        "variable name",
        "exact",
        "literal",
        "grep",
        "where is",
        "where's",
        "which file",
        "which line",
    )
    if any(signal in lowered for signal in _LITERAL_SIGNALS):
        intents.append("literal_search")
    if not intents:
        intents.append("context")
    return {"version": "ucr.intent.v1", "intents": intents, "confidence": 0.7}


def decompose_task(task: str) -> list[dict[str, Any]]:
    """Perform lightweight skill-aware decomposition without binding to one client."""
    intent = detect_intent(task)["intents"]
    steps: list[dict[str, Any]] = []
    if "literal_search" in intent:
        steps.append(
            {
                "id": "s0",
                "goal": "find exact pattern matches locally (no external LLM)",
                "preferred_tags": ["search", "literal", "grep", "exact"],
            }
        )
    if "search_context" in intent:
        steps.append({"id": "s1", "goal": "retrieve relevant context", "preferred_tags": ["search"]})
    if "mutate" in intent:
        steps.append({"id": "s2", "goal": "apply controlled change", "preferred_tags": ["storage", "docs"]})
    if "verify" in intent:
        steps.append({"id": "s3", "goal": "verify result", "preferred_tags": ["test", "metrics"]})
    if not steps:
        steps.append({"id": "s1", "goal": task, "preferred_tags": ["context"]})
    return steps


def _select_tools(
    task: str,
    registry: ToolRegistry,
    top_k: int,
    token_budget: int,
) -> list[ToolDescriptor]:
    if top_k <= 0 or token_budget <= 0:
        return []
    ranked = registry.rank(task, top_k=top_k)
    relevant = [item for item in ranked if item.score >= 0.08]
    if not relevant and ranked:
        relevant = [ranked[0]]

    # When literal_search intent is detected, ensure find_in_codebase is
    # selected and appears first — it completes locally without an external
    # LLM round-trip, saving tokens.
    intents = detect_intent(task)["intents"]
    if "literal_search" in intents:
        literal_desc = registry.get("find_in_codebase")
        if literal_desc is not None:
            relevant = [
                item for item in relevant if item.descriptor.id != "find_in_codebase"
            ]
            relevant.insert(0, RankedTool(descriptor=literal_desc, score=1.0))

    selected: list[ToolDescriptor] = []
    used_tokens = 0
    for item in relevant:
        descriptor = item.descriptor
        descriptor_tokens = descriptor_token_count(descriptor)
        if used_tokens + descriptor_tokens > token_budget:
            continue
        selected.append(descriptor)
        used_tokens += descriptor_tokens
        if len(selected) >= top_k:
            break
    return selected


def route_task(
    task: str,
    *,
    registry: ToolRegistry | None = None,
    mode: RouterMode = "recommend_tools",
    token_budget: int = 1200,
    top_k: int = 8,
) -> dict[str, Any]:
    """Route a user task to the minimal relevant tool slice.

    Supported modes:
    - ``plan_only``: return selected tools and a DAG; do not execute.
    - ``recommend_tools``: return selected tools and metrics.
    - ``execute_safe``: same plan plus execution placeholder for client-driven calls.
    """
    if mode not in {"plan_only", "recommend_tools", "execute_safe"}:
        raise ValueError("mode must be one of: plan_only, recommend_tools, execute_safe")
    if token_budget < 0 or top_k < 0:
        raise ValueError("token_budget and top_k must be non-negative")
    started = perf_counter()
    metrics = get_router_metrics()
    metrics.route_count += 1
    active_registry = registry or get_default_registry()
    cache_key = (task, mode, token_budget, top_k, active_registry.fingerprint())
    with _PLAN_CACHE_LOCK:
        if ROUTER_PLAN_CACHE_MAX_ENTRIES > 0 and cache_key in _PLAN_CACHE:
            metrics.cache_hits += 1
            _PLAN_CACHE.move_to_end(cache_key)
            cached = deepcopy(_PLAN_CACHE[cache_key])
            cached["cached"] = True
            return cached
    metrics.cache_misses += 1
    selected = _select_tools(task, active_registry, top_k=top_k, token_budget=token_budget)
    plan = build_plan(task, selected)
    all_tools = active_registry.all()
    result = {
        "version": "ucr.route_result.v1",
        "task": task,
        "mode": mode,
        "intent": detect_intent(task),
        "decomposition": decompose_task(task),
        "selected_tools": [descriptor.to_public_dict() for descriptor in selected],
        "exposure_set": {
            "version": "ucr.exposure_set.v1",
            "tools": [descriptor.id for descriptor in selected],
            "public_tools": ["route_task", "execute_plan", "search_context", "explain_plan"],
        },
        "plan": plan,
        "token_report": token_report_for_selection(all_tools, selected, token_budget),
        "execution": None if mode in {"plan_only", "recommend_tools"} else {"status": "ready"},
        "registry_fingerprint": active_registry.fingerprint(),
        "cached": False,
    }
    metrics.observe_latency(started)
    with _PLAN_CACHE_LOCK:
        if ROUTER_PLAN_CACHE_MAX_ENTRIES > 0:
            _PLAN_CACHE[cache_key] = deepcopy(result)
            while len(_PLAN_CACHE) > ROUTER_PLAN_CACHE_MAX_ENTRIES:
                _PLAN_CACHE.popitem(last=False)
    return result


def _safe_executors() -> dict[str, Callable[[dict[str, Any]], Any]]:
    return {
        "search_codebase_tool": lambda args: search_codebase(
            str(args.get("query", "")),
            resolve_project_root(str(args.get("project_root", ""))),
            top_k=int(args.get("top_k", 5)),
        ),
        "find_in_codebase": lambda args: literal_search(
            str(args.get("pattern", "")),
            resolve_project_root(str(args.get("project_root", ""))),
            case_sensitive=bool(args.get("case_sensitive", False)),
            use_regex=bool(args.get("use_regex", False)),
            file_glob=str(args.get("file_glob", "")),
        ),
    }


def execute_selected_tool(
    tool_id: str,
    arguments: dict[str, Any],
    *,
    registry: ToolRegistry | None = None,
    mode: RouterMode = "execute_safe",
    confirmed: bool = False,
) -> dict[str, Any]:
    """Execute a selected safe tool through the router safety gate."""
    metrics = get_router_metrics()
    metrics.execution_count += 1
    if mode != "execute_safe":
        return {"status": "skipped", "tool_id": tool_id, "reason": f"mode={mode}"}
    active_registry = registry or get_default_registry()
    descriptor = active_registry.get(tool_id)
    if descriptor is None:
        return {"status": "not_found", "tool_id": tool_id}

    safety = assess_tool_execution(descriptor, arguments)
    if safety.decision == SafetyDecision.BLOCK:
        metrics.blocked_count += 1
        return {
            "status": "blocked",
            "tool_id": tool_id,
            "reason": safety.reason,
            "findings": safety.findings,
        }
    if safety.decision == SafetyDecision.CONFIRM and not confirmed:
        metrics.confirmation_count += 1
        return {
            "status": "needs_confirmation",
            "tool_id": tool_id,
            "reason": safety.reason,
            "findings": safety.findings,
        }

    executor = _safe_executors().get(tool_id)
    if executor is None:
        return {
            "status": "delegated",
            "tool_id": tool_id,
            "server": descriptor.server,
            "reason": "safe, but execution belongs to the client or downstream MCP runtime",
            "arguments": redact_secrets(arguments),
        }
    return {"status": "ok", "tool_id": tool_id, "result": redact_secrets(executor(arguments))}


def execute_plan(
    plan: dict[str, Any],
    *,
    arguments_by_tool: dict[str, dict[str, Any]] | None = None,
    registry: ToolRegistry | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Execute or delegate a UCR plan through the safety gate."""
    arguments_by_tool = arguments_by_tool or {}
    results = []
    for node in plan.get("nodes", []):
        tool_id = str(node.get("tool_id", ""))
        results.append(
            execute_selected_tool(
                tool_id,
                arguments_by_tool.get(tool_id, {}),
                registry=registry,
                confirmed=confirmed,
            )
        )
    status = "blocked" if any(item.get("status") == "blocked" for item in results) else "ok"
    if any(item.get("status") == "needs_confirmation" for item in results):
        status = "needs_confirmation"
    return {"version": "ucr.execution_result.v1", "status": status, "results": results}


def search_context(query: str, project_root: str = "", top_k: int = 5) -> dict[str, Any]:
    """Client-neutral search_context public API."""
    return {
        "version": "ucr.search_context.v1",
        "query": query,
        "result": search_codebase(query, resolve_project_root(project_root), top_k=top_k),
    }


def explain_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Explain a UCR plan in client-neutral JSON."""
    nodes = plan.get("nodes", [])
    return {
        "version": "ucr.plan_explanation.v1",
        "summary": f"Plan has {len(nodes)} node(s) across {len(plan.get('stages', []))} stage(s).",
        "steps": [
            {
                "node": node.get("id"),
                "tool_id": node.get("tool_id"),
                "risk": node.get("risk_level"),
                "reason": "selected by semantic/lexical routing and ordered by planner constraints",
            }
            for node in nodes
        ],
        "edges": plan.get("edges", []),
    }


def get_route_metrics() -> dict[str, Any]:
    """Return in-process router metrics."""
    return get_router_metrics().to_dict()


def benchmark_route_task(iterations: int = 20) -> dict[str, Any]:
    """Run a tiny in-process route_task benchmark."""
    started = perf_counter()
    for _ in range(max(iterations, 1)):
        route_task("find code context and token savings", top_k=4)
    elapsed = (perf_counter() - started) * 1000.0
    return benchmark_summary(max(iterations, 1), elapsed)
