# RFC-005: Planning Engine

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines DAG construction, dependency resolution, parallel execution, fallback planning, and recovery.

## Goals

- Represent route plans as auditable DAGs.
- Support dependency-aware parallel execution.
- Define fallback, recovery, and human approval nodes.

## Non-Goals

- Become a general-purpose workflow engine.
- Execute denied or unconfirmed high-risk nodes.
- Hide planner decisions from telemetry.

## Terminology

- Plan Node: DAG vertex describing one routed operation or approval.
- Plan Edge: Dependency between nodes.
- Parallel Group: Nodes that can run concurrently.
- Fallback: Alternate path for failure, low confidence, or denied policy.

## Motivation

Once tasks are decomposed and routed, UCR needs an explicit plan that captures dependencies, policies, and recovery options.

## Design

The planner creates nodes for routed operations, context reads, approvals, and verification. Edges encode data and ordering dependencies. Parallel groups contain independent read-only or idempotent nodes. Fallbacks can retry, select an alternative tool, degrade to recommendation-only mode, request confirmation, or abort. Recovery distinguishes retryable errors from policy denies and non-idempotent failures.

## Interfaces

The route plan schema is `ucr.plan.v1`: `{"version":"ucr.plan.v1","nodes":[],"edges":[],"parallel_groups":[],"fallbacks":[],"policies":[]}`. Nodes include id, capability, inputs, outputs, idempotency key, policy refs, and timeout.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Planner plugins can add node types if they preserve DAG semantics.
- Policy providers can inject approval nodes.
- Adapters can render plans in client-specific UI.

## Security Considerations

The planner must not convert a deny into a fallback that performs the same risky action through another tool. Approval nodes must be explicit dependencies.

## Observability Considerations

Emit plan id, node count, edge count, parallel groups, fallback count, and node outcomes.

## Compatibility

Older adapters can ignore parallel groups and execute a topological order when safe.

## Trade-offs

DAG plans are more verbose than linear steps but enable parallelism, recovery, and auditability.

## Open Questions

- Which node fields are mandatory for stable v1?
- Should fallback selection be deterministic or policy-driven?
- How should partial plan completion be resumed?

## Related RFCs

- RFC-004: Skill-Aware Decomposition
- RFC-007: Dynamic Tool Exposure
- RFC-008: Execution Engine
