# RFC-003: Semantic Routing Engine

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines intent detection, embedding retrieval, ranking, scoring, filtering, and confidence calculation.

## Goals

- Rank tools and context by task relevance.
- Explain why capabilities were selected or filtered.
- Provide confidence and fallback behavior.

## Non-Goals

- Expose filtered-out tools for model tie-breaking.
- Bypass policy for better recall.
- Depend on one embedding provider.

## Terminology

- Intent: Structured interpretation of a user task.
- Candidate Set: Pre-policy list of possible tools and contexts.
- Confidence: Numeric and explanatory estimate that selected tools are sufficient.
- Risk Penalty: Ranking deduction applied to capabilities with broader blast radius.

## Motivation

Large catalogs need retrieval and ranking to avoid expose-all prompts. Routing must be explainable enough to debug and benchmark.

## Design

Routing normalizes the task, detects intent, retrieves candidates from registry and context indexes, filters denied capabilities, then scores candidates. Ranking combines semantic score, lexical score, capability match, permission fit, recency/cache hints, and risk penalty. Confidence considers top score, score margin, policy certainty, and historical success. Low-confidence results may ask for clarification, return conservative read-only exposure, or fall back to safe defaults.

## Interfaces

The routing output is `ucr.route_result.v1` with selected items, rejected items, confidence, explanations, and policy findings.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Scorers can be replaced if they return the same score explanation shape.
- Intent detectors can be rule-based, embedding-based, or hybrid.
- Feedback providers can update route priors.

## Security Considerations

Filtering happens before final exposure. The engine must not route a high-risk tool only because it is semantically similar.

## Observability Considerations

Emit candidate counts, filtered counts, selected counts, confidence, score components, and latency per stage.

## Compatibility

Adapters receive route results through stable schemas even when internal ranking changes.

## Trade-offs

Explainable multi-factor ranking is more complex than pure vector similarity but easier to tune and audit.

## Open Questions

- What confidence threshold should trigger clarification by default?
- How should historical success affect new or rarely used tools?
- Should risk penalty be global or policy-profile-specific?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-004: Skill-Aware Decomposition
- RFC-006: Context Compression
- RFC-014: Benchmarks
