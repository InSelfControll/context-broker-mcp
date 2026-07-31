"""Planner tasks for building dependency DAGs from selected tools."""

from __future__ import annotations

from typing import Any

from context_broker.router_ttc.tools.registry_tools import ToolDescriptor

_CATEGORY_ORDER = {
    "search": 10,
    "context": 20,
    "downstream": 30,
    "storage": 40,
    "docs": 50,
    "metrics": 90,
    "test": 100,
}
_TAG_ORDER = {
    "search": 10,
    "file": 20,
    "context": 25,
    "downstream": 30,
    "storage": 40,
    "docs": 50,
    "test": 100,
}


def _order_key(descriptor: ToolDescriptor) -> tuple[int, str]:
    tag_score = min((_TAG_ORDER[tag] for tag in descriptor.tags if tag in _TAG_ORDER), default=50)
    return (min(_CATEGORY_ORDER.get(descriptor.category, 50), tag_score), descriptor.id)


def _can_run_parallel(left: ToolDescriptor, right: ToolDescriptor) -> bool:
    """Return whether two tools can safely share a planner stage."""
    if left.shell_capable or right.shell_capable:
        return False
    if left.risk_level in {"high", "critical"} or right.risk_level in {"high", "critical"}:
        return False
    return _order_key(left)[0] == _order_key(right)[0]


def build_plan(task: str, selected_tools: list[ToolDescriptor]) -> dict[str, Any]:
    """Build a dependency DAG over selected tools.

    The graph remains conservative and deterministic, but now groups tools into
    parallel-safe stages when their risk and ordering class match.
    """
    ordered = sorted(selected_tools, key=_order_key)
    nodes = []
    stages: list[list[str]] = []
    for i, descriptor in enumerate(ordered):
        node_id = f"n{i + 1}"
        nodes.append(
            {
                "id": node_id,
                "tool_id": descriptor.id,
                "server": descriptor.server,
                "risk_level": descriptor.risk_level,
                "capabilities": descriptor.capabilities
                or {
                    "file": descriptor.file_capable,
                    "network": descriptor.network_capable,
                    "shell": descriptor.shell_capable,
                },
                "parallel_safe": not descriptor.shell_capable
                and descriptor.risk_level not in {"high", "critical"},
            }
        )
        if stages and all(_can_run_parallel(descriptor, ordered[int(existing[1:]) - 1]) for existing in stages[-1]):
            stages[-1].append(node_id)
        else:
            stages.append([node_id])

    edges = []
    for stage_index in range(len(stages) - 1):
        for source in stages[stage_index]:
            for target in stages[stage_index + 1]:
                source_tool = ordered[int(source[1:]) - 1].id
                target_tool = ordered[int(target[1:]) - 1].id
                edges.append({"from": source_tool, "to": target_tool})
    return {"version": "ucr.plan.v1", "task": task, "nodes": nodes, "edges": edges, "stages": stages}
