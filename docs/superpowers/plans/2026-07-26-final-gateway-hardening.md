# Final Gateway Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind execution to one expiring prepared handoff, cap the complete canonical
handoff, recover failed downstream sessions safely, and make repeated lifespans reusable.

**Architecture:** `GatewayDownstreamRuntime` owns an in-memory issuance ledger whose opaque
claims bind canonical plan/exposure digests to the runtime registry fingerprint and
generation. The synchronous gateway layer builds and counts canonical JSON for the complete
handoff; the async runtime performs safety preflight, atomic claim consumption, then real
execution. Existing TTC manager/registry boundaries remain intact.

**Tech Stack:** Python 3.13, AnyIO, FastMCP v3, tiktoken, pytest.

## Global Constraints

- `CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET` caps the complete canonical
  `ucr.external_handoff.v1` payload.
- The stable route field is only `route.exposure_set`.
- Claims are opaque, process-local, single-use after approval, and expire after 300 seconds
  by default.
- Confirmation-only responses do not consume claims; approved execution consumes before
  any possible side effect and never replays after failure.
- Gateway mode exposes exactly three FastMCP tools and never calls an LLM provider.
- Use TTC modules, `uv`, structured logging, type hints, and lines under 100 characters.

---

### Task 1: Issuance and Replay Contract

**Files:**
- Modify: `context_broker/config.py`
- Modify: `context_broker/gateway_ttc/tasks/downstream_tasks.py`
- Modify: `context_broker/gateway_ttc/tasks/gateway_tasks.py`
- Modify: `context_broker/server_ttc/tasks/gateway_tasks.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_gateway_downstreams.py`

**Interfaces:**
- Produces: `gateway_plan_claim_ttl_seconds() -> int`
- Produces: runtime handoff field
  `issuance: {"claim": str, "expires_at": int}`
- Produces: `GatewayDownstreamRuntime.execute_gateway_plan(plan, issuance_claim, ...)`
- Produces: public `execute_gateway_plan(plan_json, issuance_claim, ...)`
- Consumes: `ToolRegistry.fingerprint()`, canonical plan, and `route.exposure_set`

- [x] Add tests for missing/unissued, tampered, stale, replayed, confirmation-preserved,
  registry-drifted, and closed/restarted claims.
- [x] Run those tests and confirm they fail because no issuance ledger or public claim
  parameter exists.
- [x] Add an internal immutable issued-plan record, random opaque claim generation, expiry
  pruning, canonical digests, runtime generation, and an issuance lock.
- [x] Add a no-side-effect safety preflight; return confirmation without consumption, then
  revalidate and consume atomically before approved execution.
- [x] Run the issuance tests and confirm all pass.

### Task 2: Complete Canonical Payload Budget

**Files:**
- Modify: `context_broker/gateway_ttc/tasks/gateway_tasks.py`
- Modify: `context_broker/gateway_ttc/tools/state.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Produces: `canonical_json(value: Any) -> str`
- Produces: `canonical_token_count(value: Any, encoder: Any | None = None) -> int`
- Produces: `build_external_handoff(..., issuance: dict[str, Any] | None = None)`
- Metrics semantics: `candidate_tokens` and `sent_tokens` count complete canonical payloads;
  `context.token_count` counts canonical context items only.

- [x] Add tests comparing the encoded canonical final payload to the configured cap,
  including exact boundary, large context, and mandatory oversized task/route cases.
- [x] Run those tests and confirm current context-only accounting fails.
- [x] Build the mandatory envelope first, reject if it exceeds the cap, compute fixed-point
  whole-payload metrics, then greedily/binary trim only context item values.
- [x] Run gateway budget tests and confirm token counts and saved counts are internally
  consistent.

### Task 3: Failed Call Recovery and Repeated Lifespans

**Files:**
- Modify: `context_broker/client_ttc/tasks/connection_tasks.py`
- Modify: `context_broker/gateway_ttc/tasks/downstream_tasks.py`
- Modify: `context_broker/router_ttc/tools/registry_tools.py`
- Test: `tests/test_gateway_downstreams.py`

**Interfaces:**
- Produces: failed calls leave `ManagedDownstreamConnection.state == DEGRADED`, no session,
  and no retained raw error.
- Produces: next explicit runtime request reconnects and accepts identical rediscovery
  without replaying the failed call.
- Produces: `close()` clears claims/secrets/counts, replaces the manager, restores the
  baseline registry, and permits a second lifespan to discover identical IDs.

- [x] Add failed-call/no-replay/next-request-reconnect and two-lifespan tests.
- [x] Run them and confirm current ready-state/session/registry behavior fails.
- [x] Disconnect and degrade on call exception; permit only identical descriptor
  rediscovery on retry.
- [x] Reset registry and issuance state on close, then run lifecycle tests to GREEN.

### Task 4: Stable Schema, Documentation, and Final Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-credential-preserving-gateway-design.md`
- Modify: `docs/superpowers/plans/2026-07-26-credential-preserving-gateway.md`
- Modify: `README.md`
- Modify: `Usage.md`
- Modify: `tests/test_integrations.py`
- Modify after product commit: `CHANGELOG.md`

**Interfaces:**
- Documents only `route.exposure_set`.
- Documents complete-payload budget, required issuance claim, TTL/replay rules, degraded
  call recovery, and repeated-lifespan cleanup.

- [x] Add docs contract assertions and confirm stale `route.exposure` fails them.
- [x] Update every design/example/config table and run docs/integration tests.
- [x] Add a permitted-local-runtime test that records production AnyIO worker thread IDs;
  keep the sandbox-safe seam test.
- [x] Run focused gateway/downstream/router/docs tests, scoped Ruff, and `git diff --check`.
- [ ] Commit product/tests/docs with a concise `fix:` subject.
- [ ] Run changelog ensure/validation, coalesce same-date Unreleased headings and duplicate
  entries without dropping unique history, commit that generated cleanup separately, and
  revalidate.
- [ ] Write the ignored final-fix report with RED/GREEN evidence and security review.
