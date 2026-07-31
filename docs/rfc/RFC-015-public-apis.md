# RFC-015: Public APIs

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines stable interfaces for REST, MCP, SDK, CLI, and events.

## Goals

- Version every public API contract.
- Define MCP, REST, SDK, CLI, and event surfaces.
- Document compatibility and error behavior.

## Non-Goals

- Require all deployments to enable every interface.
- Freeze experimental APIs as stable.
- Expose storage internals as public APIs.

## Terminology

- MCP API: UCR capability exposed as an MCP tool or resource.
- REST API: Optional HTTP interface under versioned paths.
- SDK Contract: Language binding over public UCR schemas.
- Event: Versioned notification about route or execution lifecycle.

## Motivation

Client-agnostic routing requires stable contracts that adapters, plugins, CLIs, and services can share.

## Design

MCP APIs include `route_task`, `execute_selected_tool`, `register_tool_descriptor`, `list_exposure_sets`, and `get_route_metrics`. REST endpoints include `POST /v1/routes`, `POST /v1/executions`, `GET /v1/tools`, and `GET /v1/metrics`. CLI commands include `ucr route`, `ucr tools list`, `ucr benchmark`, and `ucr adapters list`. Events include `route.created`, `exposure.selected`, `execution.started`, `execution.completed`, and `policy.blocked`. Errors use typed codes: validation_error, policy_denied, confirmation_required, not_found, conflict, timeout, and backend_unavailable.

## Interfaces

The umbrella API version is `ucr.api.v1`. Request and response schemas embed specific versions such as `ucr.route_result.v1`, `ucr.execution_request.v1`, and `ucr.policy_decision.v1`. REST version negotiation uses path version plus schema version fields.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- SDKs wrap public schemas without inventing behavior.
- Adapters can expose subsets based on capability negotiation.
- Events can be delivered through logs, streams, webhooks, or client-native channels.

## Security Considerations

APIs enforce authn/authz before routing or execution. Error responses must not reveal hidden tools or sensitive policy details.

## Observability Considerations

API calls emit request id, status code, latency, schema version, and policy outcome.

## Compatibility

Breaking API changes require a new path or schema version. Deprecated fields stay readable through a documented window.

## Trade-offs

Detailed APIs improve interoperability but require stronger compatibility discipline.

## Open Questions

- Which APIs are required for a minimal server?
- How long should deprecated fields be supported?
- Should event delivery guarantee ordering?

## Related RFCs

- RFC-001: Universal Context Router Architecture
- RFC-005: Planning Engine
- RFC-007: Dynamic Tool Exposure
- RFC-009: Universal Adapter Framework
