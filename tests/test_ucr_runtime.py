"""Tests for Universal Context Router Phase 2-7 behavior."""

from __future__ import annotations

from pathlib import Path

from context_broker.router_ttc.codebase.api import (
    benchmark_route_task,
    execute_plan,
    explain_plan,
    get_route_metrics,
    route_task,
)
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor, ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets


def test_registry_supports_ucr_metadata_sqlite_and_downstream_ingestion(tmp_path: Path) -> None:
    registry = ToolRegistry(cache_dir=tmp_path)
    registry.register(
        ToolDescriptor(
            id="ctx7.query_docs",
            name="query_docs",
            server="ctx7",
            category="downstream",
            description="query library docs",
            tags=["docs", "downstream"],
            permissions=["downstream_mcp_call"],
            risk_level="medium",
            network_capable=True,
            latency_ms=12.5,
            capabilities={"network": True, "downstream": True},
        )
    )
    registry.ingest_downstream_capabilities(
        {
            "server": "github",
            "tools": [
                {"name": "list_issues", "description": "list repository issues", "input_schema": {}}
            ],
        }
    )

    reloaded = ToolRegistry(cache_dir=tmp_path)
    assert reloaded.load_sqlite()

    ctx7 = reloaded.get("ctx7.query_docs")
    assert ctx7 is not None
    assert ctx7.server == "ctx7"
    assert ctx7.latency_ms == 12.5
    assert reloaded.get("github.list_issues") is not None


def test_route_task_returns_intent_decomposition_exposure_and_plan_cache(tmp_path: Path) -> None:
    registry = ToolRegistry(cache_dir=tmp_path)
    registry.register_many(
        [
            ToolDescriptor(id="search_codebase_tool", name="search_codebase_tool", description="semantic code search", tags=["search"]),
            ToolDescriptor(id="pytest", name="pytest", description="run tests", tags=["test"], shell_capable=True),
        ]
    )

    first = route_task("find auth code and run tests", registry=registry, mode="plan_only")
    second = route_task("find auth code and run tests", registry=registry, mode="plan_only")

    assert first["version"] == "ucr.route_result.v1"
    assert "search_context" in first["intent"]["intents"]
    assert first["decomposition"]
    assert first["exposure_set"]["public_tools"] == [
        "route_task",
        "execute_plan",
        "search_context",
        "explain_plan",
    ]
    assert first["plan"]["version"] == "ucr.plan.v1"
    assert second["cached"] is True


def test_execute_plan_uses_safety_and_redacts_delegated_arguments(tmp_path: Path) -> None:
    registry = ToolRegistry(cache_dir=tmp_path)
    registry.register_many(
        [
            ToolDescriptor(id="safe", name="safe", description="safe", risk_level="low"),
            ToolDescriptor(id="deploy", name="deploy", description="deploy", risk_level="high", shell_capable=True),
        ]
    )
    plan = {
        "nodes": [
            {"id": "n1", "tool_id": "safe"},
            {"id": "n2", "tool_id": "deploy"},
        ]
    }

    result = execute_plan(
        plan,
        arguments_by_tool={"safe": {"token": "sk-secretvalue"}, "deploy": {"command": "deploy"}},
        registry=registry,
    )

    assert result["status"] == "needs_confirmation"
    safe_result = result["results"][0]
    assert safe_result["status"] == "delegated"
    assert safe_result["arguments"]["token"] == "[REDACTED]"


def test_explain_plan_metrics_benchmark_and_redaction() -> None:
    plan = {"nodes": [{"id": "n1", "tool_id": "search", "risk_level": "low"}], "stages": [["n1"]]}
    explanation = explain_plan(plan)
    assert explanation["version"] == "ucr.plan_explanation.v1"
    assert "1 node" in explanation["summary"]

    assert redact_secrets("Authorization: Bearer abcdefghijk") == "Authorization: Bearer [REDACTED]"
    bench = benchmark_route_task(iterations=1)
    metrics = get_route_metrics()
    assert bench["iterations"] == 1
    assert metrics["route_count"] >= 1
