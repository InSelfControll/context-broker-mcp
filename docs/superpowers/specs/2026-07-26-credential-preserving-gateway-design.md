# Credential-Preserving Context Gateway Design

## Summary

Add an opt-in gateway mode that makes Context Broker the sole MCP entry point for a
client session. Each request is routed and reduced locally before the client or skill
invokes an external LLM. Context Broker never receives, persists, or uses provider
credentials.

## Goals

- Route every gateway request through UCR before exposing downstream MCP tools.
- Return only task-relevant, secret-safe, token-bounded context to an external LLM.
- Keep the provider call in the client or skill so provider credentials remain outside
  Context Broker.
- Persist the gateway behavior across sessions through configuration, while retaining
  the existing default MCP surface when gateway mode is disabled.
- Measure the token budget, selected tools, and context reduction for every handoff.

## Non-goals

- Intercept requests sent directly from a client to another MCP server.
- Call an LLM provider, manage provider credentials, or implement provider-specific
  SDKs.
- Remove existing MCP tools outside explicitly enabled gateway mode.

## Request Flow

1. A client or skill registers Context Broker as its only MCP server and enables
   `CONTEXT_BROKER_GATEWAY_MODE=1`.
2. It calls `prepare_gateway_request` with the user task, optional project root, and
   a bounded token budget.
3. The gateway calls the existing UCR router to detect intent, select the smallest
   relevant downstream-MCP exposure set, and construct a route plan.
4. For workspace requests, it retrieves focused semantic context. The existing secret
   protections apply before any snippet is returned.
5. The gateway emits `ucr.external_handoff.v1`, containing the original task,
   selected tools, a redacted context bundle, route metadata, and token accounting.
6. The client or skill sends that handoff to its configured external LLM and, when
   necessary, invokes only the selected Context Broker gateway execution API.

## Public MCP Surface in Gateway Mode

- `prepare_gateway_request(task, project_root?, token_budget?, top_k?)` prepares the
  handoff and never invokes an external LLM.
- `execute_gateway_plan(plan, issuance_claim)` executes already-selected,
  policy-checked plan nodes through the existing execution path. The opaque claim is
  required and confirmation requirements remain unchanged.
- `get_gateway_status()` reports mode, configured limits, and gateway metrics.

Gateway mode hides the broad legacy tool surface from the exposed FastMCP server.
When disabled, current tool registration and behavior are unchanged.

## External Handoff Contract

`ucr.external_handoff.v1` has the following stable fields:

```json
{
  "version": "ucr.external_handoff.v1",
  "task": "original user task",
  "route": {"intent": {}, "exposure_set": {}, "plan": {}},
  "context": {"items": [], "token_count": 0, "budget": 0},
  "metrics": {"candidate_tokens": 0, "sent_tokens": 0, "saved_tokens": 0},
  "issuance": {"claim": "opaque runtime claim", "expires_at": 0}
}
```

The payload excludes environment values, provider credentials, blocked secret files,
and unselected tools. It is data, not executable instructions; the client retains
control of provider selection and execution. `context.budget` caps the complete
canonical serialized handoff, including task, route, context, metrics, and issuance.
Mandatory fields are never trimmed; preparation fails when they cannot fit. Only
`context.items` may be shortened.

## Configuration and Session Scope

- `CONTEXT_BROKER_GATEWAY_MODE=1` enables the restricted surface for every process
  session started with that environment.
- `CONTEXT_BROKER_GATEWAY_TOKEN_BUDGET` supplies the default payload limit.
- `CONTEXT_BROKER_GATEWAY_PLAN_CLAIM_TTL_SECONDS` sets the process-local claim TTL
  and defaults to 300 seconds.
- Client installation examples will register only Context Broker; downstream MCP
  servers are configured inside Context Broker as its managed clients.

The server can enforce the gateway only for requests it receives. Direct registration
of downstream MCPs in a client bypasses it and is explicitly unsupported in gateway
mode documentation.

## Security and Failure Handling

- Retrieval and secret filtering occur before the handoff is assembled.
- Tool exposure and execution continue to use existing safety and confirmation gates.
- Claims bind the exact plan, `route.exposure_set`, complete registry generation and
  fingerprint, and runtime lifetime. Missing, unknown, expired, drifted, tampered, and
  consumed claims fail before safety checks or tool calls.
- A confirmation-only response does not consume a claim. Approved execution consumes
  it atomically before side effects, and execution failures remain consumed.
- A failed established downstream call is not replayed. The session is disconnected,
  marked degraded, and retried only by the next explicit gateway request.
- If routing or retrieval fails, the gateway returns a typed, redacted failure without
  broadening context or falling back to an external provider call.
- No provider token, endpoint, or response is written to Context Broker storage.

## Tests

- Gateway mode exposes only the three gateway tools.
- A handoff contains the requested task, selected exposure, and context within budget.
- Secret-looking content and unselected tools never appear in the handoff.
- Gateway-mode retrieval records token savings.
- Legacy mode continues to expose current tools and remains backward-compatible.
- Executing a gateway plan preserves existing confirmation and redaction behavior.

## Compatibility

Gateway mode is opt-in. Existing integrations retain their current public MCP tools
until their configuration enables the gateway and removes direct downstream server
registrations.
