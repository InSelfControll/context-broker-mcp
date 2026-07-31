# RFC-012: Storage

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines Redis, vector stores, caching, persistence, indexes, TTL strategy, backup, and restore.

## Goals

- Define storage domains and backend responsibilities.
- Support local files, Redis, vector stores, and SQL-compatible metadata stores.
- Make TTL, backup, restore, and invalidation explicit.

## Non-Goals

- Mandate a single database.
- Store secrets in indexes.
- Require distributed infrastructure for local use.

## Terminology

- Storage Profile: `ucr.storage_profile.v1` configuration for a backend.
- TTL: Expiration policy for cached or temporary records.
- Durable Store: Backend intended to survive process restarts.
- Index Fingerprint: Hash used to invalidate stale embeddings or descriptors.

## Motivation

Routing depends on descriptors, embeddings, context, memories, execution logs, and benchmark artifacts. Each has different durability and latency needs.

## Design

Storage domains include tool registry cache, embedding indexes, context cache, memory store, execution logs, audit logs, and benchmark results. Local filesystem storage is the baseline. Redis can serve shared cache, short-lived context, locks, and TTL-heavy data. Vector stores hold embedding indexes. SQL-compatible stores hold metadata and audit records. TTL strategy is domain-specific. Backup covers durable stores, manifests, audit logs, and benchmark records. Restore must validate fingerprints before reusing indexes and should rebuild derived caches when source fingerprints differ.

## Interfaces

Storage profiles use `ucr.storage_profile.v1`; backends expose `read`, `write`, `delete`, `list`, `ttl`, `backup`, `restore`, and `health` operations.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Backends can be added for new vector stores or metadata stores.
- Cache policies can be plugin-provided.
- Deployment profiles can choose storage bundles.

## Security Considerations

Storage must not persist raw secrets in indexes, logs, or benchmark artifacts. Restore paths must validate integrity before use.

## Observability Considerations

Track cache hit ratio, index age, backup status, restore status, TTL expirations, and storage health checks.

## Compatibility

Derived indexes can be rebuilt from durable source records, allowing index format changes across versions.

## Trade-offs

Multiple storage domains improve correctness but complicate deployment. Local-first defaults keep small deployments simple.

## Open Questions

- Which stores are mandatory for a production profile?
- How long should audit logs be retained by default?
- Should restore require manual approval for high-risk policy stores?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-006: Context Compression
- RFC-013: Observability
- RFC-017: Deployment
