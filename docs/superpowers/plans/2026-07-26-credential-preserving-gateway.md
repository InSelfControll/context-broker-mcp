# Credential-Preserving Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in Context Broker gateway that routes first, retrieves only bounded secret-safe context, and returns a provider-neutral external-LLM handoff.

**Architecture:** A new `gateway_ttc` package composes the existing UCR router, semantic search API, tokenizer, redaction, and safe execution API without changing their internals. A dedicated server registration module exposes exactly three gateway tools when `CONTEXT_BROKER_GATEWAY_MODE=1`; normal and existing UCR-only modes remain unchanged.

**Tech Stack:** Python 3.13, FastMCP v3, tiktoken, pytest, existing TTC modules.

## Global Constraints

- Context Broker never calls an external LLM and never owns provider credentials.
- `ucr.external_handoff.v1` is the stable handoff schema.
- Gateway context must not exceed `CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET`, default `1200`.
- Gateway mode is opt-in through `CONTEXT_BROKER_GATEWAY_MODE=1`.
- Direct client registration of downstream MCP servers bypasses the gateway and remains unsupported.
- Existing non-gateway behavior must remain backward-compatible.
- Preserve unrelated working-tree changes, especially existing router and indexer edits.

---

### Task 1: Build the bounded external handoff

**Files:**
- Create: `context_broker/gateway_ttc/__init__.py`
- Create: `context_broker/gateway_ttc/tools/__init__.py`
- Create: `context_broker/gateway_ttc/tools/state.py`
- Create: `context_broker/gateway_ttc/tasks/__init__.py`
- Create: `context_broker/gateway_ttc/tasks/gateway_tasks.py`
- Modify: `context_broker/config.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Consumes: `route_task(task, mode="plan_only", token_budget, top_k)`, `search_context(query, project_root, top_k)`, `redact_secrets(value)`, `get_encoder()`, and `truncate_to_token_limit(text, encoder, token_limit)`.
- Produces: `prepare_gateway_request(task: str, project_root: str = "", token_budget: int = 1200, top_k: int = 5) -> dict[str, Any]`, `execute_gateway_plan(plan: dict[str, Any], arguments_by_tool: dict[str, dict[str, Any]] | None = None, registry: ToolRegistry | None = None, confirmed: bool = False) -> dict[str, Any]`, and `get_gateway_status() -> dict[str, Any]`.

- [ ] **Step 1: Write failing handoff tests**

Add tests that pass a real route/search payload into a pure helper and assert the stable schema, recursive secret redaction, and strict context budget:

```python
def test_build_external_handoff_redacts_and_bounds_context():
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
```

Add a second test asserting `prepare_gateway_request` calls routing before retrieval and returns an empty context bundle when `project_root=""`.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_gateway.py -q`

Expected: collection fails because `context_broker.gateway_ttc.tasks.gateway_tasks` does not exist.

- [ ] **Step 3: Implement minimal gateway state and task orchestration**

In `tools/state.py`, define a small metrics dataclass and singleton:

```python
@dataclass
class GatewayMetrics:
    prepared_requests: int = 0
    candidate_tokens: int = 0
    sent_tokens: int = 0

    @property
    def saved_tokens(self) -> int:
        return max(0, self.candidate_tokens - self.sent_tokens)


METRICS = GatewayMetrics()
```

In `gateway_tasks.py`, implement `build_external_handoff` by recursively applying `redact_secrets`, tokenizing each result after redaction, and using `truncate_to_token_limit` with the remaining budget. Only copy `intent`, `exposure_set`, and `plan` from the route result. Never copy registry internals, environment values, or provider configuration.

In `config.py`, add dynamic accessors so tests and long-lived hosts read the current process configuration without duplicating environment parsing:

```python
def gateway_mode_enabled() -> bool:
    return os.environ.get("CONTEXT_BROKER_GATEWAY_MODE", "0").lower() in {
        "1", "true", "yes", "on"
    }


def gateway_token_budget() -> int:
    return max(1, _get_env_int("CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET", 1200))
```

Implement `prepare_gateway_request` in this exact order:

```python
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
```

Reject empty tasks and non-positive token budgets with `ValueError`. `execute_gateway_plan` delegates to the existing `execute_plan`, forwarding its optional registry only for internal composition and tests; the MCP wrapper never accepts a registry from callers. `get_gateway_status` returns schema version, mode, default budget, and metrics.

- [ ] **Step 4: Run gateway tests and verify GREEN**

Run: `uv run pytest tests/test_gateway.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the core gateway**

```bash
git add context_broker/config.py context_broker/gateway_ttc tests/test_gateway.py
git commit -m "feat: add bounded external handoff gateway"
```

---

### Task 2: Expose the three-tool gateway MCP surface

**Files:**
- Create: `context_broker/server_ttc/tasks/gateway_tasks.py`
- Modify: `context_broker/server_ttc/codebase/assembly.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Consumes: the three public functions from Task 1.
- Produces: `register_gateway_tools(mcp: FastMCP) -> None` registering `prepare_gateway_request`, `execute_gateway_plan`, and `get_gateway_status`.

- [ ] **Step 1: Write the failing FastMCP surface test**

Use FastMCP v3's supported `Client` test transport:

```python
@pytest.mark.anyio
async def test_gateway_mode_exposes_only_gateway_tools(monkeypatch):
    monkeypatch.setenv("CONTEXT_BROKER_GATEWAY_MODE", "1")
    server = create_mcp_server()

    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == {
        "prepare_gateway_request",
        "execute_gateway_plan",
        "get_gateway_status",
    }
```

Add a companion test with gateway mode unset asserting representative legacy tools (`search_codebase_tool`, `route_task`, and `save_search_results`) remain exposed.

- [ ] **Step 2: Run surface tests and verify RED**

Run: `uv run pytest tests/test_gateway.py::test_gateway_mode_exposes_only_gateway_tools -q`

Expected: FAIL because gateway registration does not exist and the legacy tools are listed.

- [ ] **Step 3: Register gateway tools and branch server assembly**

Implement `register_gateway_tools` using the existing `tracked_activity`, `progress`, and JSON serialization conventions. Its tool wrappers call Task 1 APIs and do not contain routing logic.

At the top of `create_mcp_server`, before `CONTEXT_BROKER_UCR_PUBLIC_SURFACE_ONLY`, add:

```python
if os.environ.get("CONTEXT_BROKER_GATEWAY_MODE", "0").lower() in {
    "1", "true", "yes", "on"
}:
    register_gateway_tools(mcp)
    return mcp
```

Do not alter either the existing UCR-only branch or normal registration sequence.

- [ ] **Step 4: Run surface tests and verify GREEN**

Run: `uv run pytest tests/test_gateway.py -q`

Expected: PASS.

- [ ] **Step 5: Commit MCP gateway registration**

```bash
git add context_broker/server_ttc/tasks/gateway_tasks.py context_broker/server_ttc/codebase/assembly.py tests/test_gateway.py
git commit -m "feat: add restricted gateway MCP surface"
```

---

### Task 3: Verify execution safety and observability

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `context_broker/gateway_ttc/tasks/gateway_tasks.py`
- Modify: `context_broker/gateway_ttc/tools/state.py`

**Interfaces:**
- Consumes: `execute_plan` safety decisions and Task 1 metrics.
- Produces: cumulative status payload `ucr.gateway_status.v1` and unchanged `ucr.execution_result.v1` execution results.

- [ ] **Step 1: Write failing execution and metrics tests**

Add a real low-risk registry descriptor and assert `execute_gateway_plan` preserves the existing execution result schema. Add a medium-risk descriptor and assert execution returns `needs_confirmation` until `confirmed=True`. Prepare two handoffs and assert status metrics accumulate candidate, sent, and saved tokens without including payload content.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_gateway.py -q`

Expected: FAIL on missing cumulative status fields or changed safety behavior.

- [ ] **Step 3: Implement the minimal metrics updates**

Update metrics only after a handoff is assembled. `get_gateway_status()` must return:

```python
{
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
```

Store numbers only; never store tasks, context, credentials, or LLM responses.

- [ ] **Step 4: Run focused and router regression tests**

Run: `uv run pytest tests/test_gateway.py tests/test_ucr_runtime.py tests/test_token_slim_router.py -q`

Expected: PASS.

- [ ] **Step 5: Commit safety and metrics coverage**

```bash
git add context_broker/gateway_ttc tests/test_gateway.py
git commit -m "test: verify gateway safety and metrics"
```

---

### Task 4: Document persistent client and skill integration

**Files:**
- Modify: `README.md`
- Modify: `Usage.md`
- Modify: `AGENTS.md`
- Test: `tests/test_integrations.py`

**Interfaces:**
- Consumes: `CONTEXT_BROKER_GATEWAY_MODE`, `CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET`, and the three gateway MCP tools.
- Produces: copyable client configuration and a workspace rule requiring skills/agents to call `prepare_gateway_request` before external LLM handoff.

- [ ] **Step 1: Write failing documentation-contract tests**

Add assertions that README/Usage document both environment variables, all three gateway tools, the sole-MCP registration requirement, and the explicit limitation that direct downstream MCP registration bypasses enforcement. Extend the AGENTS validation assertion to require `prepare_gateway_request` in the Context Broker rule block.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_integrations.py -q`

Expected: FAIL because gateway configuration and skill guidance are absent.

- [ ] **Step 3: Add deployment and skill guidance**

Document a client-neutral config that sets:

```json
{
  "CONTEXT_BROKER_GATEWAY_MODE": "1",
  "CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET": "1200",
  "CONTEXT_BROKER_AUTO_LOAD_ENV": "0"
}
```

State that clients must register only Context Broker and configure Context7, GitHub, filesystem, memory, and other MCPs as Context Broker downstream servers. Add an AGENTS rule: every skill or agent that needs external-LLM context calls `prepare_gateway_request` first and forwards only its returned handoff.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run: `uv run pytest tests/test_integrations.py -q`

Expected: PASS.

- [ ] **Step 5: Commit integration documentation**

```bash
git add README.md Usage.md AGENTS.md tests/test_integrations.py
git commit -m "docs: require gateway-first client integration"
```

---

### Task 5: Final verification and changelog health

**Files:**
- Modify if required by project tooling: `CHANGELOG.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: a fully verified gateway feature with documented history.

- [ ] **Step 1: Run the complete test and lint suite**

Run:

```bash
uv run pytest
uv run ruff check .
```

Expected: all tests pass and Ruff reports no findings.

- [ ] **Step 2: Validate changelog coverage**

Run `validate_changelog_tool` for the repository. If the new feature commits are reported as undocumented, run `ensure_changelog_tool`, inspect the generated entry, and rerun validation.

- [ ] **Step 3: Verify the live MCP surface in both modes**

Start an in-process FastMCP client twice: once with gateway mode enabled and once disabled. Confirm gateway mode lists exactly three tools and normal mode includes the legacy search and router tools.

- [ ] **Step 4: Commit only generated changelog changes, if any**

```bash
git add CHANGELOG.md
git commit -m "docs: record credential-preserving gateway"
```
