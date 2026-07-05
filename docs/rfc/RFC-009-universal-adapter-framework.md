# RFC-009: Universal Adapter Framework

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines client abstraction, capability detection, transport, streaming, and version negotiation.

## Goals

- Keep client-specific behavior outside core.
- Support current and future MCP-compatible clients through adapters.
- Define capability detection and version negotiation.

## Non-Goals

- Make any reference adapter target required.
- Implement client UI behavior in core.
- Prefer one client ecosystem.

## Terminology

- Adapter: Client or transport integration outside the core router.
- Capability Matrix: Feature report for dynamic exposure, streaming, confirmation, and delegation.
- Reference Adapter Target: Compatibility target, not a core dependency.
- Version Negotiation: Handshake that selects compatible contract versions.

## Motivation

Different clients expose different MCP, streaming, confirmation, and tool-visibility capabilities. Adapters isolate those differences.

## Design

Adapters implement `ucr.adapter.v1`. They detect capabilities, bind transport, publish exposure sets, request confirmation, stream events, and delegate tool execution when needed. Reference adapter targets include Claude Code, Codex CLI, Cursor, Hermes Agent, Goose, OpenHands, Aider, Gemini CLI, Continue.dev, and Cline. These are compatibility targets only. A capability matrix records dynamic exposure, streaming, confirmation, and proxy support.

## Interfaces

The adapter interface is `ucr.adapter.v1` with `detect_capabilities`, `publish_exposure_set`, `request_confirmation`, `stream_event`, and `execute_delegated_tool`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- New adapters can be distributed as plugins.
- Transport implementations can support stdio, HTTP, or client-native channels.
- Adapters can add UI-specific rendering outside core.

## Security Considerations

Adapters must not weaken core policy. If a client cannot enforce a policy, the adapter must report degraded capability and choose conservative fallback.

## Observability Considerations

Track adapter name, adapter version, negotiated contracts, fallback mode, streaming errors, and delegated executions.

## Compatibility

Version negotiation allows adapters to select the newest mutually supported schema version.

## Trade-offs

Adapters increase integration work but keep the core portable and testable.

## Open Questions

- What is the minimum adapter compliance profile?
- Should reference adapters share a conformance suite?
- How should unsupported client features be reported to users?

## Related RFCs

- RFC-001: Universal Context Router Architecture
- RFC-007: Dynamic Tool Exposure
- RFC-015: Public APIs
