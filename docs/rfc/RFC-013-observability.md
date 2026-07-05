# RFC-013: Observability

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines metrics, tracing, logging, performance telemetry, and health monitoring.

## Goals

- Make routing, policy, planning, and execution observable.
- Support metrics, traces, logs, telemetry, and health checks.
- Provide evidence for benchmarks and operations.

## Non-Goals

- Log secrets or sensitive arguments.
- Require one telemetry vendor.
- Make safety-critical events optional.

## Terminology

- Telemetry Event: Redacted event emitted by routing, policy, planning, or execution.
- Trace Context: Correlation ids spanning route, plan, node, and execution.
- Metric: Numeric observation such as token reduction or route latency.
- Health Check: Machine-readable readiness or liveness signal.

## Motivation

A router that changes visible tools and context must explain its decisions. Observability makes token savings, failures, and policy actions measurable.

## Design

Metrics include token reduction percent, exposure count, route latency, retrieval latency, planning latency, execution latency, safety blocks, fallback count, and cache hit ratio. Traces carry request id, route id, plan id, node id, and execution id. Logs are structured JSON with redaction. Health checks report registry, storage, adapter, policy, index, and sandbox status. OpenTelemetry export is supported through optional adapters.

## Interfaces

Telemetry events use `ucr.telemetry_event.v1` with `event_type`, `timestamp`, `ids`, `metrics`, `outcome`, and redacted `attributes`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Exporters can target logs, metrics systems, traces, or local files.
- Plugins can add domain metrics.
- Adapters can display route explanations to users.

## Security Considerations

Telemetry must redact secrets, sensitive paths, and tool arguments according to policy. Audit logs are separate from debug logs.

## Observability Considerations

This RFC defines observability; implementations should test that each major route stage emits required signals.

## Compatibility

Telemetry consumers should ignore unknown attributes and rely on stable event names and ids.

## Trade-offs

More telemetry improves debugging but can increase storage volume and redaction complexity.

## Open Questions

- Which metrics are required for minimal conformance?
- Should route explanations be stored by default?
- How should telemetry sampling interact with audit requirements?

## Related RFCs

- RFC-008: Execution Engine
- RFC-014: Benchmarks
- RFC-017: Deployment
