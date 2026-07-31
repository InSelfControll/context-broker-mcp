# RFC-014: Benchmarks

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines token reduction, latency, memory usage, planning accuracy, execution accuracy, and scalability benchmarks.

## Goals

- Measure token reduction, latency, memory, planning accuracy, execution accuracy, and scalability.
- Use reproducible public or synthetic data.
- Compare expose-all, static allowlist, and UCR dynamic routing baselines.

## Non-Goals

- Use restricted datasets.
- Tune only for one client.
- Hide failed benchmark cases.

## Terminology

- Benchmark Run: Reproducible measurement record.
- Expose-All Baseline: Baseline where every tool/context is visible.
- Static Allowlist Baseline: Fixed tool set chosen without task-specific retrieval.
- Route Accuracy: Whether selected capabilities satisfy the task.

## Motivation

UCR success claims need repeatable measurements, not anecdotes. Benchmarks also prevent regressions in routing quality and safety.

## Design

Benchmark suites include synthetic tool catalog, public OSS repo context, MCP tool selection, safety regression, and planner DAG scenarios. Baselines are expose-all, static allowlist, and UCR dynamic routing. Each run records catalog size, queries, selected tools, token counts, latency percentiles, memory peak, route accuracy, execution accuracy, safety outcomes, seeds, and environment metadata.

## Interfaces

Benchmark records use `ucr.benchmark_run.v1` with suite, scenario, baseline, metrics, artifacts, and environment fields.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Projects can add public benchmark suites.
- Adapters can add conformance benchmarks.
- Plugins can contribute synthetic catalogs.

## Security Considerations

Benchmark fixtures must avoid secrets and non-public data. Safety benchmarks should include malicious synthetic prompts and dangerous command fixtures.

## Observability Considerations

Benchmark runs produce telemetry summaries that can be compared over time.

## Compatibility

Benchmark schemas should remain stable so historical results stay comparable.

## Trade-offs

Reproducible benchmarks require maintenance, but they turn token-reduction goals into measurable acceptance criteria.

## Open Questions

- Which public repositories should be canonical fixtures?
- What route accuracy threshold is acceptable for v1?
- How should benchmark noise be normalized across hardware?

## Related RFCs

- RFC-003: Semantic Routing Engine
- RFC-006: Context Compression
- RFC-013: Observability
- RFC-016: Testing Strategy
