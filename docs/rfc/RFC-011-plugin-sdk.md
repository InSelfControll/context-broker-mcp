# RFC-011: Plugin SDK

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines plugin lifecycle, discovery, registration, capabilities, version compatibility, and marketplace readiness.

## Goals

- Allow extension without core changes.
- Define plugin lifecycle and manifest validation.
- Prepare for optional ecosystem distribution.

## Non-Goals

- Run untrusted plugin code without isolation.
- Require a central marketplace.
- Let plugins bypass policy.

## Terminology

- Plugin Manifest: `ucr.plugin_manifest.v1` declaration of plugin metadata.
- Extension Point: Named place where a plugin can add behavior.
- Permission Request: Plugin-declared capability requirement.
- Activation: Runtime transition from registered to usable.

## Motivation

A universal router needs external contributors to add descriptors, rankers, policies, adapters, and storage backends without forking core.

## Design

Plugin lifecycle is discover, validate, load, register, activate, deactivate, and unload. A plugin declares capabilities, permissions, compatible core versions, extension points, and optional storage needs. Validation checks manifest schema, checksums where available, permission requests, and version compatibility. Marketplace readiness means metadata is complete and verifiable without requiring any marketplace.

## Interfaces

Plugins use `ucr.plugin_manifest.v1` with `id`, `version`, `entrypoint`, `capabilities`, `permissions`, `compatible_core`, and `extension_points`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Plugins can contribute registry providers, rankers, policy providers, storage backends, adapters, and benchmark suites.
- Core can add new extension points in minor versions when optional.

## Security Considerations

Plugin loading is a high-risk boundary. Permissions are explicit, defaults are least privilege, and plugins cannot grant themselves execution authority.

## Observability Considerations

Track discovered, rejected, loaded, activated, deactivated, and failed plugins with reasons.

## Compatibility

Plugins declare compatible core ranges. Incompatible plugins remain discovered but inactive.

## Trade-offs

A plugin SDK increases extensibility but expands the attack surface and compatibility burden.

## Open Questions

- Should plugins run in-process, out-of-process, or both?
- What signing or checksum requirements should stable plugins meet?
- Which extension points should be stable in v1?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-010: Security Architecture
- RFC-012: Storage
