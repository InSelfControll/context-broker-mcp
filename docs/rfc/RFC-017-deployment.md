# RFC-017: Deployment

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines standalone, Docker, Podman, Kubernetes, home lab, and enterprise deployment models.

## Goals

- Support local, container, Kubernetes, home lab, and enterprise deployment.
- Define configuration, health checks, upgrade, and migration policy.
- Avoid managed-platform requirements.

## Non-Goals

- Require a managed cloud platform.
- Assume one secrets manager.
- Make distributed deployment mandatory.

## Terminology

- Deployment Profile: `ucr.deployment_profile.v1` description of a runtime topology.
- Health Check: Liveness and readiness probe for a component.
- Migration: Versioned state or config transition.
- Home Lab: Small self-hosted deployment using portable components.

## Motivation

UCR should run for a single developer and scale to larger deployments without changing core contracts.

## Design

Standalone mode runs one process with local storage. Docker and Podman modes mount config and persistent volumes. Kubernetes separates router, cache, vector store, and telemetry when needed. Home lab mode favors simple containers and local backups. Enterprise mode adds high availability, policy integration, audit retention, and centralized observability. Health checks include liveness, readiness, registry freshness, storage reachability, adapter negotiation, and sandbox availability. Upgrade policy requires schema compatibility checks before start. Migration policy applies versioned config and storage migrations with dry-run support and backup guidance.

## Interfaces

Deployment profiles use `ucr.deployment_profile.v1` with mode, components, storage, ports, health checks, upgrade policy, and migration policy.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Operators can add deployment templates.
- Storage profiles can be swapped per environment.
- Adapters can be enabled per deployment profile.

## Security Considerations

Secrets are injected by the deployment environment and are never stored in docs examples. Production profiles should enable audit retention and stricter policy defaults.

## Observability Considerations

Deployments expose health checks, startup lifecycle events, resource metrics, and migration status.

## Compatibility

Rolling upgrades require compatible API and storage versions or explicit maintenance mode.

## Trade-offs

Supporting many topologies increases documentation burden, but it keeps UCR portable.

## Open Questions

- Which deployment profile is the reference for conformance tests?
- Should migrations run automatically or require operator approval?
- What health check failures should remove a node from service?

## Related RFCs

- RFC-008: Execution Engine
- RFC-012: Storage
- RFC-013: Observability
