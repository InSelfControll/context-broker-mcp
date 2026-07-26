"""Tests for credential-preserving gateway handoffs."""

from __future__ import annotations

import json

import pytest

from context_broker.gateway_ttc.tasks import gateway_tasks
from context_broker.gateway_ttc.tasks.gateway_tasks import build_external_handoff


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
