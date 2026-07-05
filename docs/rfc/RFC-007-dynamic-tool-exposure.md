# RFC-007: Dynamic Tool Exposure

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines minimal exposure, capability negotiation, tool filtering, permission checks, and context-aware visibility.

## Goals

- Expose only task-relevant tools and context.
- Negotiate client capability without core client logic.
- Provide fallback for clients without dynamic hiding.

## Non-Goals

- Treat hiding as authorization.
- Assume all clients support identical exposure controls.
- Reveal denied tools as hidden suggestions.

## Terminology

- Exposure Set: Versioned bundle of visible tools, context, memories, and policies.
- Capability Negotiation: Adapter handshake that describes what dynamic controls a client supports.
- Visibility Filter: Policy and relevance gate applied before model exposure.
- Static Fallback: Recommendation mode for clients without dynamic hiding.

## Motivation

Default expose-all tool lists waste tokens and invite tool misuse. Dynamic exposure makes the model see only what the task needs.

## Design

The router turns selected route results into an exposure set. Before inclusion, each item passes relevance, permission, risk, and context checks. Capability negotiation tells the adapter whether it can hide tools, proxy calls, wrap tools, or only display recommendations. Static fallback returns a recommended allowlist and safety notes for clients with limited controls.

## Interfaces

The exposure set schema is `ucr.exposure_set.v1`: `{"version":"ucr.exposure_set.v1","tools":[],"contexts":[],"memories":[],"policies":[],"token_budget":0}`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Adapters can implement exposure through native hiding, tool proxying, or recommendation-only mode.
- Policy plugins can add visibility constraints.
- Ranking plugins can propose alternative exposure sets.

## Security Considerations

A tool must be authorized even if it is visible. High-risk visibility can require confirmation or a narrowed wrapper.

## Observability Considerations

Track exposed tools, hidden tools, exposure tokens, denied items, adapter mode, and fallback mode.

## Compatibility

Recommendation-only mode preserves usefulness for clients without dynamic exposure APIs.

## Trade-offs

Dynamic exposure reduces tokens but requires adapter support for strongest enforcement.

## Open Questions

- Should high-risk tools ever be visible before confirmation?
- How should exposure sets be cached per task?
- What is the minimum fallback contract for simple clients?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-006: Context Compression
- RFC-009: Universal Adapter Framework
- RFC-010: Security Architecture
