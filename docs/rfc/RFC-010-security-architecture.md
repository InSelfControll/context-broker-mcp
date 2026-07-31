# RFC-010: Security Architecture

Status: Draft
Version: 0.1.0
Last Updated: 2026-07-05
Audience: maintainers, adapter authors, plugin authors, MCP client integrators

## Summary

Defines threat model, authentication, authorization, sandboxing, secret handling, injection defenses, policy engine, and audit logging.

## Goals

- Define UCR threat model and defense layers.
- Prevent unsafe routing, exposure, and execution.
- Make policy decisions explicit and auditable.

## Non-Goals

- Promise perfect prevention against all adversarial input.
- Let prompt text override authorization.
- Rely on client-side hiding as the only security boundary.

## Terminology

- Policy Engine: Service that returns allow, deny, or confirm decisions.
- Threat Model: Enumerated adversarial and accidental failure cases.
- Sandbox: Restricted execution environment selected by risk.
- Audit Event: Redacted security record of a policy or execution decision.

## Motivation

UCR controls what an agent can see and do. That makes security architecture central to correctness, not an optional feature.

## Design

Threats include malicious prompt content, compromised tool metadata, command injection, path traversal, secret exfiltration, overbroad exposure, confused deputy attacks, and unsafe plugins. Controls include authentication, authorization, sandboxing, secret redaction, prompt-injection defense, command-injection defense, path traversal checks, policy evaluation, and audit logging. Risk levels are low, medium, high, and critical.

## Interfaces

The policy decision schema is `ucr.policy_decision.v1`: `{"version":"ucr.policy_decision.v1","decision":"allow|deny|confirm","reason":"string","findings":[]}`.

All public runtime payloads include a `version` field. Consumers must ignore unknown optional fields and reject unsupported major schema versions with a typed compatibility error.

## Extension Points

- Policy providers can integrate local rules or organization rules.
- Sandbox providers can add execution isolation profiles.
- Secret scanners can contribute detectors with redacted findings.

## Security Considerations

Security decisions are made before exposure and before execution. Untrusted content is treated as data. Audit logs must include decision reasons without storing sensitive values.

## Observability Considerations

Security telemetry includes denies, confirmations, scanner findings, sandbox selections, and audit event ids.

## Compatibility

Policy profiles can become stricter without breaking schema compatibility; weakening defaults requires explicit migration notes.

## Trade-offs

Stronger checks can block legitimate workflows, but confirmation and scoped permissions provide safer escape hatches.

## Open Questions

- Which operations require mandatory human confirmation?
- How should policy profiles be distributed and versioned?
- What evidence is required before accepting a new sandbox provider?

## Related RFCs

- RFC-002: Universal Tool Registry
- RFC-007: Dynamic Tool Exposure
- RFC-008: Execution Engine
- RFC-011: Plugin SDK
