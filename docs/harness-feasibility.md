# Context Broker harness feasibility

Status: design assessment, 2026-09-05. The messaging gateway and native agent
execution adapters described here are not implemented or deployed by this change.

A standalone harness is feasible. Keep Context Broker as the shared project memory,
retrieval, routing, and handoff service. Add an execution runtime and channel adapters
around it. An MCP server alone cannot intercept every host prompt or control an editor.

| Component | Reuse / implementation path | Current gap |
| --- | --- | --- |
| Project memory | Existing shared service, selective history lookup, immutable model handoffs | Host must send questions and checkpoints through the broker |
| Provider runtime | Adapter interface for streaming messages, tools, model capabilities, cancellation, usage, and authentication | Current completion worker only produces read-only proposals through an OpenAI-compatible endpoint |
| Cursor execution | Use Cursor CLI ACP sessions; expose the broker to Cursor through its MCP configuration | Implement ACP client, permission/question forwarding, cancellation, and session binding |
| Messaging | Separate Telegram, Discord, and Teams adapters delivering a common authenticated request envelope | Bot registrations, credentials, channel authorization, approvals, and delivery queues |
| Task execution | Durable task state and bounded workers, isolated project worktrees, host tool permissions | Never treat a provider response or CLI exit alone as verified task completion |

[Cursor documents ACP](https://cursor.com/docs/cli/acp) over stdio, including session
creation/resumption, prompts, permission requests, questions, and cancellation. It
also supports project/user MCP configurations. This provides an official integration
boundary for remote control of Cursor CLI; it does not imply control of arbitrary
open GUI conversations. Preserve failures in the broker's own task state even when
an external host's todo schema has no failed state.

[Hermes already offers a messaging gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
including Telegram, Discord, and Teams. A first deployment could use Hermes as the
channel/execution host with this broker as its project memory service. A fully owned
harness requires its own adapters and orchestration, but should reuse the broker's
existing memory and failure contracts instead of duplicating them.

“All providers” should mean an extensible, capability-tested adapter boundary, not
an unconditional compatibility promise. OpenAI-compatible endpoints are one adapter;
non-compatible APIs and provider-specific authentication need separate adapters.
[Hermes' provider guide](https://hermes-agent.nousresearch.com/docs/developer-guide/adding-providers)
identifies the same distinctions. Preserve the user's exact model and reasoning
choice; never silently substitute a provider or enable High reasoning. Unsupported
capabilities must produce a failed task with a useful reason.

The common request envelope should bind authenticated platform/account/channel/user
IDs to an explicit allowlisted project and session. Never trust a project path from
message text. Keep credentials in runtime secrets, redact logs, restrict command/tool
permissions, and prevent untrusted history from overriding policy. Approval buttons
must bind to the exact user, task, model, proposed action, and expiry. Reject replayed
or cross-channel approvals; handle duplicate messages idempotently.

For native channels, use the [Telegram Bot API](https://core.telegram.org/bots/api),
[Discord interactions](https://docs.discord.com/developers/interactions/receiving-and-responding),
and the [Teams SDK / Microsoft 365 Agents SDK](https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/overview).
Verify each platform's authentication and webhook requirements. Telegram long polling
can avoid opening an inbound port for the initial deployment. Do not expose the
broker's local bearer-token service directly to the internet.

Suggested implementation order:

1. A local durable execution loop: lookup relevant issue history, assemble bounded
   context, execute with explicit permissions, record outcomes, and save a handoff.
2. Cursor ACP adapter with permission/question forwarding and verified cancellation.
3. Telegram adapter with an account allowlist and single-use approval callbacks.
4. Discord and Teams adapters using the same task/session/approval contracts.
5. Additional provider adapters with contract tests for tool calls, model identity,
   streaming, context limits, billing metrics, and failure propagation.

Acceptance requires real provider and native client checks plus channel tests for
unauthorized users, replayed approvals, duplicate delivery, cancellation, restart
recovery, project isolation, bounded queues, and truthful failed/completed outcomes.
