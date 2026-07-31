# RFC-016: Testing Strategy

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines unit, integration, regression, security, performance, load, and chaos testing strategy.

## Goals

- Test correctness, safety, performance, and resilience.
- Use synthetic MCP servers and public fixtures.
- Define CI requirements and public-only test data policy.

## Non-Goals

- Depend on live external services for core CI.
- Treat snapshots as proof of semantic correctness.
- Skip human review for security-sensitive changes.

## Terminology

- Golden Fixture: Stable input/output fixture reviewed for regression detection.
- Synthetic MCP Server: Test server with deterministic tools and schemas.
- Chaos Test: Fault injection scenario for resilience checks.
- Public-Only Test Data Policy: Rule that tests use synthetic or public data only.

## Motivation

A routing layer can fail silently by exposing too much, selecting the wrong tool, or hiding necessary context. Tests must catch these regressions.

## Design

Unit tests cover registry, routing, planning, compression, exposure, policy, storage, adapters, and plugins. Integration tests use synthetic MCP servers. Regression tests use golden fixtures with reviewed expected routes and policy outcomes. Security tests cover injection, path traversal, secret handling, dangerous commands, plugin permissions, and confused deputy cases. Performance tests measure latency and memory. Load tests scale catalog and context size. Chaos tests simulate storage loss and adapter failure. The public-only test data policy requires synthetic or public data only. CI requirements include unit, docs, security regression, benchmark smoke, and lint gates.

## Interfaces

Test suite metadata uses `ucr.test_suite.v1` with suite name, fixture set, required services, expected metrics, and data classification.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Plugins can add conformance tests.
- Adapters can add capability-specific fixtures.
- Benchmark suites can reuse golden fixtures.

## Security Considerations

Security regression tests must fail closed when fixtures are ambiguous. Test logs must not contain secrets.

## Observability Considerations

CI should publish route accuracy, token reduction, latency, safety blocks, and flaky test counts.

## Compatibility

Golden fixtures should include schema versions and migration notes when expected outputs change.

## Trade-offs

Golden fixtures can become brittle, but they provide high-value regression signals for routing behavior.

## Open Questions

- Who approves updates to golden fixtures?
- Which chaos tests belong in every CI run versus nightly runs?
- What minimum benchmark smoke test should gate merges?

## Related RFCs

- RFC-010: Security Architecture
- RFC-014: Benchmarks
- RFC-017: Deployment
