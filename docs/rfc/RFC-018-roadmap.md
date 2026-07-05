# RFC-018: Roadmap

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines future capabilities, research topics, experimental features, and long-term architecture.

## Goals

- Describe near-, medium-, and long-term capabilities.
- Mark experimental features clearly.
- Keep roadmap aligned with open-source governance.

## Non-Goals

- Promise dates for research work.
- Commit to platform-specific integrations in core.
- Treat experimental capabilities as stable.
- Promise or depend on commercial-only integrations.

## Terminology

- Roadmap Item: Capability with maturity, dependency, and exit criteria.
- Experimental Feature: Opt-in capability excluded from stability guarantees.
- Federated Registry: Multiple registries participating through common contracts.
- Exit Criteria: Evidence needed to graduate roadmap work.

## Motivation

The roadmap helps contributors understand sequencing while preserving flexibility as MCP clients, tools, and routing techniques evolve.

## Design

Near-term work includes completing core APIs, maturing registry/routing, adapter examples, and benchmark suite. Medium-term work includes plugin SDK, distributed storage, richer policy engine, and observability dashboard. Long-term work includes self-optimizing routing, federated registries, portable execution sandboxes, and an open plugin ecosystem. UCR should avoid promising proprietary integrations; adapter work must remain optional and outside core. Experimental features are opt-in, documented, and excluded from stability guarantees until accepted by later RFCs.

## Interfaces

Roadmap metadata uses `ucr.roadmap.v1` with capability status, maturity, dependencies, risks, and exit criteria.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Community RFCs can propose new roadmap items.
- Plugins and adapters can graduate from experimental to stable through conformance tests.
- Benchmarks can define exit criteria for routing improvements.

## Security Considerations

Experimental features default off when they affect policy, execution, or data exposure. Security review is an exit criterion for stable status.

## Observability Considerations

Roadmap tracking should publish maturity, benchmark status, open risks, and accepted RFC links.

## Compatibility

Roadmap items do not create compatibility promises until their RFC and schemas are accepted.

## Trade-offs

A public roadmap encourages contribution but can be mistaken for a commitment; clear maturity labels reduce that risk.

## Open Questions

- Which experimental features should be excluded from packaged releases?
- What evidence graduates self-optimizing routing to stable?
- Should adapter examples have their own roadmap track?

## Related RFCs

- RFC-000: Vision
- RFC-014: Benchmarks
- RFC-015: Public APIs
- RFC-016: Testing Strategy
