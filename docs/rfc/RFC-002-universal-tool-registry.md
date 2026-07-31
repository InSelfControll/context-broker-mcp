# RFC-002: Universal Tool Registry

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines tool metadata, discovery, capabilities, versioning, permissions, schemas, embeddings, and caching.

## Goals

- Define `ucr.tool_descriptor.v1`.
- Support MCP introspection, manifests, plugins, and adapter capability catalogs.
- Enable retrieval, filtering, permission checks, and cache invalidation.
- Define a permission model and risk taxonomy.

## Non-Goals

- Store executable code in descriptors.
- Require one embedding backend.
- Treat visibility as authorization.

## Terminology

- Tool Descriptor: `ucr.tool_descriptor.v1` metadata record for a callable capability.
- Capability: Declared action class such as file read, network read, shell execution, or storage write.
- Permission: Policy-controlled grant required before a tool is exposed or executed.
- Risk Taxonomy: Low, medium, high, and critical classification used by policy and confirmation flows.

## Motivation

Tool routing requires normalized metadata across MCP servers and adapters. Without a registry, routing is opaque and token-heavy.

## Design

`ucr.tool_descriptor.v1` includes required fields `id`, `name`, `version`, `description`, `schema`, `schema_summary`, `capabilities`, `permissions`, and `risk_level`; optional fields include `category`, `tags`, `source`, `embedding_ref`, and `cache_key`. Validation rejects missing versions, unknown risk levels, invalid schemas, and descriptor ids that collide without compatible versions. The risk taxonomy is low for read-only bounded actions, medium for writes in bounded stores, high for shell/network side effects, and critical for destructive, credential, production, or broad-scope operations. Permissions are named grants evaluated before exposure and execution.

## Interfaces

The registry public object is `ucr.tool_descriptor.v1`; registry responses return descriptor arrays plus a registry fingerprint.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Plugins can register descriptors after manifest validation.
- Adapters can submit capability descriptors for client-native actions.
- Embedding providers can store vectors referenced by `embedding_ref`.

## Security Considerations

Descriptors are untrusted until validated. Compromised metadata can cause over-exposure, so policy must check source trust, permissions, risk taxonomy, and schema bounds.

## Observability Considerations

Registry metrics include descriptor count, invalid descriptor count, embedding freshness, cache hit ratio, and fingerprint changes.

## Compatibility

Minor descriptor fields may be added if old consumers ignore unknown fields. Removing required fields requires a new version.

## Trade-offs

Rich descriptors improve routing and safety but require more upkeep from tool providers.

## Open Questions

- Should descriptor schemas use JSON Schema only or allow protocol-native schemas?
- How should conflicting descriptor versions be resolved across registries?
- Which risk taxonomy changes require a major version?

## Related RFCs

- RFC-003: Semantic Routing Engine
- RFC-007: Dynamic Tool Exposure
- RFC-010: Security Architecture
- RFC-011: Plugin SDK
