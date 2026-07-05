# RFC-008: Execution Engine

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines safe execution, retry policy, timeouts, rollback, idempotency, and result handling.

## Goals

- Execute approved plan nodes safely.
- Define retry, timeout, rollback, and idempotency behavior.
- Capture structured results and audit events.

## Non-Goals

- Run arbitrary commands without sandboxing.
- Guarantee perfect rollback for external systems.
- Retry non-idempotent operations blindly.

## Terminology

- Execution Request: Policy-checked operation request.
- Execution Result: Structured outcome with output, errors, timing, and audit ids.
- Idempotency Key: Stable key preventing unsafe duplicate side effects.
- Compensating Action: Best-effort action that mitigates a completed operation.

## Motivation

Routing selects capabilities, but execution must enforce policy and operational safety at call time.

## Design

Execution validates `ucr.execution_request.v1`, checks policy, selects a sandbox, executes the tool, captures stdout/result/error metadata, records audit logs, and returns `ucr.execution_result.v1`. Retry policy uses bounded backoff for transient errors only. Timeouts are capability- and risk-specific. Rollback hooks are declared per operation and labeled as true rollback or compensating action. Idempotency keys prevent duplicate side effects.

## Interfaces

Execution input is `ucr.execution_request.v1`; result output is `ucr.execution_result.v1`; retries use `ucr.retry_policy.v1`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Sandbox providers can support local process, container, remote worker, or no-execution modes.
- Tool executors can register rollback hooks.
- Adapters can delegate execution to client-native runtimes.

## Security Considerations

Every execution is rechecked even if the tool was exposed. Shell, network write, credential, and destructive operations require stricter sandboxing and confirmation.

## Observability Considerations

Emit execution id, node id, sandbox id, duration, retry count, timeout, rollback status, and policy decision id.

## Compatibility

If an adapter owns execution, UCR can return delegated status while preserving result schemas.

## Trade-offs

Central execution improves safety but may duplicate client runtime features. Delegation is simpler but less uniform.

## Open Questions

- Which sandbox profile is required for critical operations?
- How should rollback failures be represented?
- Can idempotency keys be adapter-provided?

## Related RFCs

- RFC-005: Planning Engine
- RFC-010: Security Architecture
- RFC-013: Observability
- RFC-017: Deployment
