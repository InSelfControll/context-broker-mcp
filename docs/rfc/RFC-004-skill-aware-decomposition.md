# RFC-004: Skill-Aware Decomposition

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines task decomposition, iterative refinement, planning heuristics, subtask routing, and feedback loops.

## Goals

- Use skills to split complex tasks into routeable subtasks.
- Avoid over-decomposition for simple tasks.
- Refine decomposition from feedback.

## Non-Goals

- Let skills override policy.
- Treat untrusted retrieved text as trusted skill instructions.
- Require decomposition for every request.

## Terminology

- Skill: Procedural metadata that helps decompose or verify a task.
- Subtask: Routeable unit with its own tool/context requirements.
- Feedback Loop: Refinement input from tool results, traces, or user corrections.
- Over-Decomposition: Splitting a task into unnecessary units that increase overhead.

## Motivation

Complex tasks often need different tools at different times. Skill-aware decomposition improves planning quality by creating smaller routing decisions.

## Design

The decomposer classifies task type, extracts constraints, matches skill metadata, proposes subtasks, maps each subtask to tool/context needs, and revises the split based on feedback. Feedback includes tool failures, execution traces, user corrections, confidence changes, and reviewer findings. Heuristics avoid creating subtasks unless they change capability needs, dependency order, or verification.

## Interfaces

The decomposition artifact is `ucr.decomposition.v1` with task id, subtasks, constraints, skill references, dependencies, and confidence.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Skill catalogs can be local, plugin-provided, or adapter-provided.
- Decomposition strategies can be specialized by domain.
- Feedback processors can update skill relevance.

## Security Considerations

Skills are procedural hints, not authority. User instructions and security policy remain higher priority than skill text.

## Observability Considerations

Track selected skills, subtask count, decomposition latency, refinement count, and rejected subtasks.

## Compatibility

Clients that cannot consume subtasks still receive a final plan or exposure set.

## Trade-offs

Decomposition can improve accuracy but increases planning overhead and may fragment simple tasks.

## Open Questions

- What default subtask limit prevents over-planning?
- How should skill conflicts be resolved?
- When should user clarification happen before decomposition?

## Related RFCs

- RFC-003: Semantic Routing Engine
- RFC-005: Planning Engine
- RFC-016: Testing Strategy
