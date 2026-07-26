"""Tests for credential-preserving gateway handoffs."""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

from context_broker.gateway_ttc.tasks import gateway_tasks
from context_broker.gateway_ttc.tasks.gateway_tasks import (
    build_external_handoff,
    get_gateway_status,
)
from context_broker.indexer_ttc.tools.model_tools import get_encoder
from context_broker.server_ttc.codebase.assembly import create_mcp_server


@pytest.mark.anyio
async def test_gateway_mode_exposes_only_gateway_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent gateway mode from exposing legacy MCP capabilities."""
    monkeypatch.setenv("CONTEXT_BROKER_GATEWAY_MODE", "1")
    server = create_mcp_server()

    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == {
        "prepare_gateway_request",
        "execute_gateway_plan",
        "get_gateway_status",
    }


@pytest.mark.anyio
async def test_default_mode_keeps_representative_legacy_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep established MCP tools available when gateway mode is not enabled."""
    monkeypatch.delenv("CONTEXT_BROKER_GATEWAY_MODE", raising=False)
    server = create_mcp_server()

    async with Client(server) as client:
        tool_names = {tool.name for tool in await client.list_tools()}

    assert {"search_codebase_tool", "route_task", "save_search_results"} <= tool_names


def test_build_external_handoff_redacts_and_bounds_context() -> None:
    """Prevent gateway handoffs from leaking secrets or exceeding their context budget."""
    route = {
        "intent": {"kind": "code_search"},
        "exposure_set": {"tools": ["context-broker.search_context"]},
        "plan": {"version": "ucr.plan.v1", "nodes": []},
    }
    search = {
        "results": [
            {"path": "app.py", "content": "API_KEY=super-secret\n" + "word " * 200},
        ],
        "context_tokens": 205,
    }

    handoff = build_external_handoff(
        "inspect token=super-secret",
        route_result=route,
        search_result=search,
        token_budget=20,
    )

    assert handoff["version"] == "ucr.external_handoff.v1"
    assert handoff["task"] == "inspect token=[REDACTED]"
    assert handoff["context"]["token_count"] <= 20
    assert "super-secret" not in json.dumps(handoff)
    assert handoff["metrics"]["saved_tokens"] > 0


def test_build_external_handoff_bounds_serialized_allowlisted_context() -> None:
    """Prevent paths or metadata from bypassing the serialized context token budget."""
    handoff = build_external_handoff(
        "inspect result",
        route_result={"intent": {}, "exposure_set": {}, "plan": {}},
        search_result={
            "results": [
                {
                    "path": "nested/" + "long-path/" * 200,
                    "content": "useful context " * 50,
                    "metadata": "oversized metadata " * 200,
                }
            ]
        },
        token_budget=20,
    )

    items = handoff["context"]["items"]
    serialized_tokens = len(get_encoder().encode(json.dumps(items)))

    assert items
    assert set(items[0]) == {"path", "content"}
    assert "oversized metadata" not in json.dumps(items)
    assert serialized_tokens <= 20
    assert handoff["context"]["token_count"] == serialized_tokens


def test_prepare_gateway_request_caps_budget_to_current_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent callers from requesting more context than the configured gateway limit."""
    routed_budgets: list[int] = []

    def route(task: str, **kwargs: object) -> dict[str, object]:
        routed_budgets.append(int(kwargs["token_budget"]))
        return {"intent": {}, "exposure_set": {}, "plan": {"nodes": []}}

    monkeypatch.setenv("CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET", "7")
    monkeypatch.setattr(gateway_tasks, "route_task", route)

    handoff = gateway_tasks.prepare_gateway_request("inspect project", token_budget=100)

    assert routed_budgets == [7]
    assert handoff["context"]["budget"] == 7


def test_gateway_status_accumulates_prepared_handoff_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report cumulative token reduction only after a handoff has been prepared."""
    before = get_gateway_status()["metrics"]

    def route(task: str, **kwargs: object) -> dict[str, object]:
        return {"intent": {}, "exposure_set": {}, "plan": {"nodes": []}}

    def search(task: str, project_root: str, top_k: int) -> dict[str, object]:
        return {"result": {"results": [{"path": "app.py", "content": "word " * 50}]}}

    monkeypatch.setattr(gateway_tasks, "route_task", route)
    monkeypatch.setattr(gateway_tasks, "search_context", search)

    handoff = gateway_tasks.prepare_gateway_request(
        "inspect project", project_root="/workspace", token_budget=5
    )
    after = get_gateway_status()["metrics"]

    assert after["prepared_requests"] == before["prepared_requests"] + 1
    assert after["candidate_tokens"] == before["candidate_tokens"] + handoff["metrics"]["candidate_tokens"]
    assert after["sent_tokens"] == before["sent_tokens"] + handoff["metrics"]["sent_tokens"]
    assert after["saved_tokens"] == after["candidate_tokens"] - after["sent_tokens"]


def test_prepare_gateway_request_routes_before_retrieval_and_skips_empty_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route first, then retrieve only when a project root is supplied."""
    calls: list[str] = []

    def route(task: str, **kwargs: object) -> dict[str, object]:
        calls.append(f"route:{task}")
        assert kwargs == {"mode": "plan_only", "token_budget": 10, "top_k": 2}
        return {"intent": {}, "exposure_set": {}, "plan": {"nodes": []}}

    def search(task: str, project_root: str, top_k: int) -> dict[str, object]:
        calls.append(f"search:{task}")
        assert project_root == "/workspace"
        assert top_k == 2
        return {"result": {"results": [], "context_tokens": 0}}

    monkeypatch.setattr(gateway_tasks, "route_task", route)
    monkeypatch.setattr(gateway_tasks, "search_context", search)

    gateway_tasks.prepare_gateway_request(
        "inspect project", project_root="/workspace", token_budget=10, top_k=2
    )
    empty_project = gateway_tasks.prepare_gateway_request(
        "inspect project", token_budget=10, top_k=2
    )

    assert calls == ["route:inspect project", "search:inspect project", "route:inspect project"]
    assert empty_project["context"] == {"items": [], "token_count": 0, "budget": 10}


def test_gateway_rejects_invalid_handoff_requests() -> None:
    """Reject invalid public inputs before routing or returning a handoff."""
    with pytest.raises(ValueError, match="task"):
        gateway_tasks.prepare_gateway_request("", token_budget=1)
    with pytest.raises(ValueError, match="token budget"):
        gateway_tasks.prepare_gateway_request("inspect", token_budget=0)
