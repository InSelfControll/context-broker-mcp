# RFC-000: Vision

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines UCR's mission, goals, non-goals, terminology, architecture overview, and design philosophy.

## Goals

- Establish UCR as a universal intelligence layer between AI agents and external capabilities.
- Reduce token consumption by more than 95% on realistic workloads.
- Improve planning quality and execution accuracy through relevant context and tool routing.
- Remain vendor-neutral, MCP-first, open-source friendly, and extensible.

## Non-Goals

- Replace MCP or define a competing agent protocol.
- Require any specific client, hosted service, or commercial product.
- Place adapter-specific behavior in the core router.
- Guarantee safety without policy, sandboxing, confirmation, and audit logging.

## Terminology

- Context Item: Text, code, memory, artifact metadata, or execution result that may be routed into a task.
- Tool Descriptor: Versioned metadata for a callable capability and its risk profile.
- Adapter: Component that translates UCR contracts into client or transport behavior.
- Plugin: Optional extension that contributes descriptors, policies, rankings, storage, or adapters.
- Exposure Set: Minimal tools, contexts, memories, and policies made visible for a task.

## Motivation

Agents perform worse when every tool, memory, and context item is always visible. UCR narrows the visible universe to task-relevant capabilities, keeping the model focused while retaining a universal compatibility layer.

## Design

The platform routes user requests through intent detection, skill-aware decomposition, semantic retrieval, ranking, DAG planning, dynamic exposure, safe execution, and telemetry. Core contracts are public and versioned. Adapters map those contracts to clients. Plugins add capabilities through declared extension points.

## Interfaces

RFC-000 defines the project charter contract `ucr.vision.v1`. It is a governance and documentation interface, not a runtime payload.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Future RFCs extend this vision with runtime contracts.
- Governance can add new Accepted RFCs without changing the charter goals.
- Adapters and plugins must state how they preserve this charter.

## Security Considerations

The vision treats security as a primary design constraint, not an add-on. Any implementation that optimizes token savings by weakening policy, secret handling, or auditability is outside the vision.

## Observability Considerations

Success is measured through token reduction, route quality, execution accuracy, safety events, and adapter compatibility metrics.

## Compatibility

The vision is compatible with MCP-compliant clients and future clients through adapters. Core contracts should survive client churn.

## Trade-offs

A broad vision risks scope creep. The counterweight is a strict non-goal list and versioned RFC process.

## Open Questions

- Should RFC-000 become Accepted immediately as the charter?
- Who approves changes to core design principles?
- Which minimum benchmarks prove the vision?

## Related RFCs

- RFC-001: Universal Context Router Architecture
- RFC-015: Public APIs
- RFC-018: Roadmap
