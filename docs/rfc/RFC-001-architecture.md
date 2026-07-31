# RFC-001: Universal Context Router Architecture

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines UCR high-level architecture, execution pipeline, core services, extension model, lifecycle, and interfaces.

## Goals

- Define client-neutral core services and dependency direction.
- Specify the execution pipeline from request ingestion to telemetry.
- Make lifecycle states explicit and observable.
- Define extension seams for adapters, plugins, storage, ranking, and policy.

## Non-Goals

- Specify every backend implementation.
- Embed client-specific logic in core.
- Mandate one embedding model, vector store, or deployment topology.

## Terminology

- Request Gateway: Normalizes client input into router requests.
- Core Service: Client-neutral module that owns one UCR concern.
- Lifecycle State: Observable phase such as registry load, index warmup, request routing, execution, result capture, or shutdown.
- Adapter Boundary: Dependency direction where adapters import core contracts but core does not import adapters.

## Motivation

A universal router needs clear module boundaries so routing, policy, adapters, and execution can evolve independently.

## Design

Core services are Request Gateway, Intent Detector, Context Index, Tool Registry, Skill Decomposer, Planner, Policy Engine, Execution Engine, Adapter Layer, and Observability Pipeline. The lifecycle states are: startup, registry load, index warmup, request routing, execution, result capture, and shutdown. Startup validates config and plugins. Registry load reads descriptors and computes fingerprints. Index warmup prepares embeddings and caches. Request routing builds exposure sets. Execution runs approved nodes. Result capture records outputs and telemetry. Shutdown flushes durable state and releases resources.

## Interfaces

Primary architecture contracts are `ucr.request.v1`, `ucr.route_context.v1`, `ucr.route_result.v1`, `ucr.exposure_set.v1`, and `ucr.execution_result.v1`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Adapters import core contracts; core never imports adapters.
- Ranking strategies implement a scorer interface.
- Policy providers implement allow, deny, confirm decisions.
- Storage providers implement cache, index, and audit stores.

## Security Considerations

Every pipeline stage has a policy boundary. Descriptors are validated before registry admission, context is scanned before exposure, and execution is checked even if a tool was previously exposed.

## Observability Considerations

Each lifecycle state emits a state transition event and duration. Route ids correlate request routing, planning, exposure, execution, and result capture.

## Compatibility

Adapters can support a subset of capabilities as long as they report capability negotiation accurately.

## Trade-offs

Strict layering adds adapter work but prevents core lock-in. Lifecycle observability adds implementation overhead but shortens debugging.

## Open Questions

- Should index warmup be eager, lazy, or deployment-configurable by default?
- Which lifecycle states require persistent audit records?
- Should adapters be loaded before or after plugin validation?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-003: Semantic Routing Engine
- RFC-008: Execution Engine
- RFC-013: Observability
