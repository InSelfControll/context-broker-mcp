# Universal Context Router RFC Index

Universal Context Router (UCR) is a vendor-neutral, MCP-first, client-agnostic platform for routing context, tools, memory, and execution across AI agents and MCP servers.

## RFC Status Legend

- Draft: Initial proposal under active development.
- Accepted: Approved as architectural direction.
- Superseded: Replaced by a newer RFC.
- Deprecated: Retained for history but no longer recommended.

## RFCs

| RFC | Title | Status |
| --- | --- | --- |
| [RFC-000](./RFC-000-vision.md) | Vision | Draft |
| [RFC-001](./RFC-001-architecture.md) | Universal Context Router Architecture | Draft |
| [RFC-002](./RFC-002-universal-tool-registry.md) | Universal Tool Registry | Draft |
| [RFC-003](./RFC-003-semantic-routing-engine.md) | Semantic Routing Engine | Draft |
| [RFC-004](./RFC-004-skill-aware-decomposition.md) | Skill-Aware Decomposition | Draft |
| [RFC-005](./RFC-005-planning-engine.md) | Planning Engine | Draft |
| [RFC-006](./RFC-006-context-compression.md) | Context Compression | Draft |
| [RFC-007](./RFC-007-dynamic-tool-exposure.md) | Dynamic Tool Exposure | Draft |
| [RFC-008](./RFC-008-execution-engine.md) | Execution Engine | Draft |
| [RFC-009](./RFC-009-universal-adapter-framework.md) | Universal Adapter Framework | Draft |
| [RFC-010](./RFC-010-security-architecture.md) | Security Architecture | Draft |
| [RFC-011](./RFC-011-plugin-sdk.md) | Plugin SDK | Draft |
| [RFC-012](./RFC-012-storage.md) | Storage | Draft |
| [RFC-013](./RFC-013-observability.md) | Observability | Draft |
| [RFC-014](./RFC-014-benchmarks.md) | Benchmarks | Draft |
| [RFC-015](./RFC-015-public-apis.md) | Public APIs | Draft |
| [RFC-016](./RFC-016-testing-strategy.md) | Testing Strategy | Draft |
| [RFC-017](./RFC-017-deployment.md) | Deployment | Draft |
| [RFC-018](./RFC-018-roadmap.md) | Roadmap | Draft |

## Documentation Rules

- Use only public repositories, public protocols, or synthetic examples.
- Keep every RFC independently understandable.
- Version every public interface.
- Keep client-specific logic in adapters, never in the core router.
- Explain rationale, trade-offs, extension points, and security considerations in every RFC.

## Recommended Reading Order

Start with RFC-000 and RFC-001 for project framing, then read RFC-002 through RFC-008 for routing behavior, RFC-009 through RFC-013 for extensibility and operations, and RFC-014 through RFC-018 for validation, deployment, and roadmap.
