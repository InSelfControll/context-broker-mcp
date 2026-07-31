# RFC-006: Context Compression

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines duplicate removal, prompt summarization, context prioritization, token budgeting, and compression policies.

## Goals

- Reduce context while preserving task evidence.
- Support lossless, extractive, abstractive, and hybrid policies.
- Protect secrets and policy text from unsafe summaries.

## Non-Goals

- Use summaries as proof when exact evidence is required.
- Compress secrets into model-visible text.
- Rewrite security policy semantics.

## Terminology

- Compression Policy: Rule for reducing context while preserving task evidence.
- Lossless Compression: Exact-preserving reduction such as deduplication.
- Extractive Compression: Selecting original snippets.
- Abstractive Compression: Summarizing trusted content with explicit loss.

## Motivation

Context routing must fit within token budgets. Compression lets UCR preserve useful evidence while avoiding irrelevant or repeated content.

## Design

Compression starts with duplicate removal and canonicalization. It then scores context by relevance, trust, recency, and required evidence. Lossless policies preserve exact text. Extractive policies select snippets. Abstractive policies summarize trusted non-policy content. Hybrid policies combine exact citations and summaries. Token budgets reserve space for policy, user task, exposure set, route plan, evidence, and answer.

## Interfaces

Compression decisions are represented as `ucr.compression_policy.v1`; output bundles use `ucr.context_bundle.v1` with retained items, omitted items, token counts, and loss notes.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Projects can add domain-specific snippet extractors.
- Storage backends can provide precomputed summaries.
- Adapters can request stricter lossless modes.

## Security Considerations

Secret-bearing content is blocked before compression. Policy and authorization text should be lossless or referenced, not paraphrased.

## Observability Considerations

Record original tokens, compressed tokens, saved percent, compression mode, omitted item count, and evidence citations.

## Compatibility

Clients that do not understand compression metadata still receive plain text bundles.

## Trade-offs

Abstractive summaries save tokens but can lose nuance; exact snippets cost more but are safer for evidence.

## Open Questions

- When should a task require lossless-only compression?
- How should compression quality be benchmarked?
- Can summaries be cached across policy profiles?

## Related RFCs

- RFC-003: Semantic Routing Engine
- RFC-007: Dynamic Tool Exposure
- RFC-012: Storage
- RFC-014: Benchmarks
