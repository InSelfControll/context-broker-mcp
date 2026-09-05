"""Consent, exact model, snapshot integrity, concurrency, and review gates."""

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import Client

from context_broker.delegation_ttc.tasks.delegation_tasks import DelegationRuntime
from context_broker.delegation_ttc.tools.worker_tools import CompletionWorker, WorkerError


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Consent:
    def __init__(self, decision="Split task", action="accept"):
        self.decision, self.action = decision, action
        self.questions = []

    async def elicit(self, message, **kwargs):
        self.questions.append(message)
        return SimpleNamespace(action=self.action, data=self.decision)


class Worker:
    def __init__(self):
        self.calls = []
        self.active = 0
        self.peak = 0
        self.approved = True

    def endpoint(self):
        return "https://example.invalid/v1/chat/completions"

    async def complete(self, model, prompt):
        self.calls.append((model, prompt))
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            if prompt.startswith("Review"):
                return dict(
                    approved=self.approved,
                    covered_criteria=[0],
                    conflicts=[],
                    missing_context=[],
                    verification_plan=["Run regression tests"],
                    synthesis="Integrate the two proposals and validate.",
                )
            return dict(
                status="proposed",
                summary="proposal",
                proposed_changes=["proposed patch"],
                evidence=["source inspection"],
                risks=[],
            )
        finally:
            self.active -= 1


def request(tmp_path, ctx=None):
    (tmp_path / "main.py").write_text("keep_this_context = 42\n")
    return dict(
        task="Fix the large feature",
        model="exact-model-123",
        subtasks=["Inspect parser", "Inspect renderer"],
        context="Do not change the public API. Preserve prior decision X.",
        acceptance_criteria=["Public API preserved"],
        files=["main.py"],
        project_root=str(tmp_path),
        ctx=ctx or Consent(),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "action,decision",
    [("decline", "Split task"), ("cancel", "Split task"), ("accept", "Keep one agent")],
)
async def test_no_workers_without_explicit_split(tmp_path, action, decision):
    worker = Worker()
    args = request(tmp_path, Consent(decision, action))
    result = await DelegationRuntime(worker).run(**args)
    assert result["status"] == "single_agent"
    assert not worker.calls
    assert "exact-model-123" in args["ctx"].questions[0]


@pytest.mark.anyio
async def test_parallel_workers_keep_context_model_and_review(tmp_path):
    worker = Worker()
    result = await DelegationRuntime(worker).run(**request(tmp_path))
    assert result["status"] == "ready_for_integration"
    assert worker.peak == 2
    assert len(worker.calls) == 3
    assert {m for m, _ in worker.calls} == {"exact-model-123"}
    for _, prompt in worker.calls:
        assert "keep_this_context" in prompt
        assert "Preserve prior decision X." in prompt
        assert "Public API preserved" in prompt
    assert len({a["context_digest"] for a in result["agents"]}) == 1
    assert result["applied"] is False and result["tests_executed"] is False


@pytest.mark.anyio
async def test_unsupported_client_does_not_launch(tmp_path):
    worker = Worker()
    args = request(tmp_path, object())
    result = await DelegationRuntime(worker).run(**args)
    assert result["status"] == "confirmation_required"
    assert not worker.calls


@pytest.mark.anyio
async def test_snapshot_change_while_asking_requires_new_proposal(tmp_path):
    class ChangingConsent(Consent):
        async def elicit(self, *args, **kwargs):
            (tmp_path / "main.py").write_text("changed = True\n")
            return await super().elicit(*args, **kwargs)

    worker = Worker()
    result = await DelegationRuntime(worker).run(**request(tmp_path, ChangingConsent()))
    assert result["status"] == "failed"
    assert result["failure_code"] == "stale_context"
    assert not worker.calls


@pytest.mark.anyio
async def test_bad_review_never_counts_as_complete(tmp_path):
    worker = Worker()
    worker.approved = False
    result = await DelegationRuntime(worker).run(**request(tmp_path))
    assert result["status"] == "failed"
    assert result["failure_code"] == "review_failed"


@pytest.mark.anyio
async def test_worker_failure_cancels_siblings_and_releases_capacity(tmp_path):
    class FailingWorker(Worker):
        async def complete(self, model, prompt):
            if prompt.endswith("Inspect parser"):
                await asyncio.sleep(0.02)
                raise WorkerError("failed")
            self.active += 1
            try:
                await asyncio.sleep(30)
            finally:
                self.active -= 1

    worker = FailingWorker()
    runtime = DelegationRuntime(worker)
    args = request(tmp_path)
    result = await runtime.run(**args)
    assert result["status"] == "failed"
    assert worker.active == 0
    runtime.worker = Worker()
    assert (await runtime.run(**args))["status"] == "ready_for_integration"


@pytest.mark.anyio
@pytest.mark.parametrize("bad_files", [["../outside.py"], ["main.py"] * 31])
async def test_invalid_context_never_launches(tmp_path, bad_files):
    worker = Worker()
    args = request(tmp_path)
    args["files"] = bad_files
    result = await DelegationRuntime(worker).run(**args)
    assert result["status"] == "failed"
    assert result["failure_reason"]
    assert not worker.calls and not args["ctx"].questions


@pytest.mark.anyio
async def test_provider_exact_model_and_no_truncated_outputs(monkeypatch):
    """Exercise the actual HTTP adapter against a controlled HTTP transport."""
    import httpx
    import json
    from context_broker.delegation_ttc.tools import worker_tools

    monkeypatch.setattr(worker_tools, "LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setattr(worker_tools, "LLM_API_KEY", "")
    actual_client = httpx.AsyncClient
    actual_model = "wrong-model"
    finish = "stop"

    def handler(req):
        assert json.loads(req.content)["model"] == "requested-model"
        return httpx.Response(
            200,
            json={
                "model": actual_model,
                "choices": [
                    {"finish_reason": finish, "message": {"content": '{"summary":"done"}'}}
                ],
            },
        )

    monkeypatch.setattr(
        worker_tools.httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(
            transport=httpx.MockTransport(handler), trust_env=False, **kwargs
        ),
    )
    with pytest.raises(WorkerError, match="different model"):
        await CompletionWorker().complete("requested-model", "prompt")
    actual_model = "requested-model"
    finish = "length"
    with pytest.raises(WorkerError, match="incomplete"):
        await CompletionWorker().complete("requested-model", "prompt")
    finish = "stop"
    assert await CompletionWorker().complete("requested-model", "prompt") == {"summary": "done"}


@pytest.mark.anyio
async def test_mcp_tool_exposes_consent_and_model_contract():
    from context_broker.server import create_mcp_server

    async with Client(create_mcp_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    tool = tools["delegate_large_task"]
    assert "model" in tool.inputSchema["required"]
    assert "BEFORE" in tool.description


@pytest.mark.anyio
@pytest.mark.parametrize("decision", ["Split task", "Keep one agent"])
async def test_mcp_elicitation_roundtrip_controls_real_dispatch(tmp_path, monkeypatch, decision):
    from context_broker.server import create_mcp_server
    from context_broker.delegation_ttc.tasks import delegation_tasks

    worker = Worker()
    monkeypatch.setattr(delegation_tasks, "CompletionWorker", lambda: worker)
    questions = []

    async def answer(message, response_type, params, context):
        assert not worker.calls
        questions.append(message)
        return {"value": decision}

    args = request(tmp_path)
    del args["ctx"]
    async with Client(create_mcp_server(), elicitation_handler=answer) as client:
        result = await client.call_tool("delegate_large_task", args)
    assert len(questions) == 1
    if decision == "Split task":
        assert result.data["status"] == "ready_for_integration"
        assert len(worker.calls) == 3
    else:
        assert result.data["status"] == "single_agent"
        assert not worker.calls


@pytest.mark.anyio
async def test_no_unbounded_batch_queue(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingConsent(Consent):
        async def elicit(self, *args, **kwargs):
            entered.set()
            await release.wait()
            return await super().elicit(*args, **kwargs)

    runtime = DelegationRuntime(Worker())
    args = request(tmp_path, WaitingConsent())
    first = asyncio.create_task(runtime.run(**args))
    await entered.wait()
    try:
        assert (await runtime.run(**args))["status"] == "busy"
    finally:
        release.set()
        await first


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["missing_criterion", "conflict", "missing_context"])
async def test_reviewer_cannot_approve_incomplete_handoff(tmp_path, kind):
    class IncompleteReviewer(Worker):
        async def complete(self, model, prompt):
            result = await super().complete(model, prompt)
            if prompt.startswith("Review"):
                if kind == "missing_criterion":
                    result["covered_criteria"] = []
                elif kind == "conflict":
                    result["conflicts"] = ["Two proposals conflict"]
                else:
                    result["missing_context"] = ["Missing API contract"]
            return result

    result = await DelegationRuntime(IncompleteReviewer()).run(**request(tmp_path))
    assert result["status"] == "failed"
    assert result["failure_code"] == "review_failed"


@pytest.mark.anyio
async def test_oversize_context_is_rejected_not_truncated(tmp_path):
    worker = Worker()
    args = request(tmp_path)
    args["context"] = "X" * 65000
    result = await DelegationRuntime(worker).run(**args)
    assert result["status"] == "failed"
    assert "nothing was truncated" in result["failure_reason"]
    assert not args["ctx"].questions and not worker.calls


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://user:pass@example.com/v1",
        "file:///tmp/socket",
        "https://example.com/v1?key=secret",
    ],
)
def test_provider_destination_restrictions(monkeypatch, url):
    from context_broker.delegation_ttc.tools import worker_tools

    monkeypatch.setattr(worker_tools, "LLM_BASE_URL", url)
    with pytest.raises(WorkerError):
        CompletionWorker().endpoint()


@pytest.mark.anyio
async def test_failed_batch_returns_completed_handoffs(tmp_path):
    class PartlyFailingWorker(Worker):
        async def complete(self, model, prompt):
            if prompt.endswith("Inspect renderer"):
                await asyncio.sleep(0.04)
                raise WorkerError("failed")
            return await super().complete(model, prompt)

    result = await DelegationRuntime(PartlyFailingWorker()).run(**request(tmp_path))
    assert result["status"] == "failed"
    assert len(result["agents"]) == 1
    assert result["agents"][0]["agent"] == 1
    assert result["agents"][0]["context_digest"] == result["context_digest"]


def test_router_offers_user_choice_for_large_task(tmp_path):
    from context_broker.router_ttc.tasks.router_tasks import route_task
    from context_broker.router_ttc.tools.registry_tools import ToolRegistry

    result = route_task(
        "Split this task between multiple agents", registry=ToolRegistry(cache_dir=tmp_path)
    )
    offer = result["delegation_offer"]
    assert offer["requires_user_choice"] and offer["model_required"]
    assert offer["tool"] == "delegate_large_task"
    assert result["execution"] is None


@pytest.mark.anyio
async def test_provider_total_deadline(monkeypatch):
    from context_broker.delegation_ttc.tools import worker_tools

    monkeypatch.setattr(worker_tools, "REQUEST_TIMEOUT_SECONDS", 0.01)

    class SlowWorker(CompletionWorker):
        async def _complete(self, model, prompt):
            await asyncio.sleep(10)

    with pytest.raises(WorkerError, match="total request deadline"):
        await SlowWorker().complete("model", "prompt")


@pytest.mark.anyio
async def test_secret_context_never_reaches_consent_or_provider(tmp_path):
    worker = Worker()
    args = request(tmp_path)
    args["context"] = "-----BEGIN " + "PRIVATE KEY-----\nfixture only\n"
    result = await DelegationRuntime(worker).run(**args)
    assert result["status"] == "failed"
    assert not worker.calls and not args["ctx"].questions


def test_snapshot_rejects_undecodable_context(tmp_path):
    from context_broker.delegation_ttc.tasks.delegation_tasks import snapshot

    (tmp_path / "broken.py").write_bytes(b"content\xff")
    with pytest.raises(ValueError, match="unreadable"):
        snapshot(str(tmp_path), ["broken.py"])


@pytest.mark.anyio
async def test_agent_declared_failure_cannot_pass_review(tmp_path):
    class FailedWorker(Worker):
        async def complete(self, model, prompt):
            result = await super().complete(model, prompt)
            result.update(status="failed", failure_reason="Required parser source is missing")
            return result

    worker = FailedWorker()
    result = await DelegationRuntime(worker).run(**request(tmp_path))
    assert result["status"] == "failed"
    assert result["completed"] is False
    assert result["failure_reason"] == "Required parser source is missing"
    assert result["failed_agents"]
    assert not any(prompt.startswith("Review") for _, prompt in worker.calls)


@pytest.mark.anyio
async def test_mcp_failure_preserves_error_flag_and_reason(tmp_path):
    from context_broker.server import create_mcp_server

    args = request(tmp_path)
    args.pop("ctx")
    args["model"] = ""
    async with Client(create_mcp_server()) as client:
        result = await client.call_tool_mcp("delegate_large_task", args)
    assert result.isError
    assert result.structuredContent["status"] == "failed"
    assert result.structuredContent["completed"] is False
    assert "exact model ID" in result.structuredContent["failure_reason"]
