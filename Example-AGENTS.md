# AGENTS.md — AI agent instructions

This file tells coding agents how to work **in this repository** and what tools to use. **Copy it into the root of each new project** you create, then edit the [Project profile](#project-profile) and [Repository conventions](#repository-conventions-washield) sections; keep [MCP integration](#mcp-integration-portable) and [Context Broker](#context-broker-mcp-user-context-broker) unless your stack replaces them.

---

## Project goals

WaShield provides **short links** for **WhatsApp group invite URLs** with **geo allow/block lists**, **honeypot / bot friction**, **click analytics**, and a **browser dashboard**. **Clerk** authenticates users; **Polar** drives subscriptions and per-tier limits. The product goal is to reduce invite leakage and abuse while keeping operations simple for non-developers.

## Purpose and overview

Agents implement features and fixes in a **Go monolith** (module root `src/`) backed by **SQLite** (and optional **Turso** per `docs/OPERATIONS.md`). Public behavior must match **documented API rules** (for example WhatsApp-only target URLs). Billing and entitlements must stay consistent across **Polar metadata**, **API responses**, and the **dashboard UI**.

## Tech stack

- **Language / runtime:** Go 1.22 (`src/go.mod`)
- **HTTP:** `net/http`-style handlers in `src/internal/web/` (no separate SPA build in-repo)
- **Database:** SQLite file or libSQL; schema and migrations as used by the repo
- **Auth:** Clerk (JWT validation, webhooks)
- **Billing:** Polar (`github.com/polarsource/polar-go`), Standard Webhooks for Polar events

## Architecture

One process exposes **HTML dashboard**, **JSON APIs**, **redirect** (`/{shortCode}`), and **webhook** routes. Domain logic sits in `**src/internal/*`** packages; `**src/cmd/server**` wires configuration and starts the listener. Templates and inline scripts live beside web handlers under `**src/internal/web/**`.

## Project structure


| Path                    | Role                                               |
| ----------------------- | -------------------------------------------------- |
| `src/cmd/server/`       | Process entrypoint                                 |
| `src/internal/link/`    | Links, validation, storage                         |
| `src/internal/billing/` | Polar client, plans, sync, pricing                 |
| `src/internal/auth/`    | Clerk helpers                                      |
| `src/internal/web/`     | HTTP handlers, templates, landing                  |
| `docs/`                 | Operations runbook and `docs/solutions/` learnings |


## Coding conventions

- **Match the file** you edit: naming, error style, and patterns already present.
- **Format** Go with `gofmt` (or editor equivalent).
- **Authoritative behavior** for auth, ownership, and plan limits is **server-side**; UI hints must not be the only enforcement.
- **No secrets** in source; use env vars documented in `.env.example` / `README.md`.

## Testing

From `**src/`**, run `**go test ./...**`. Add or extend tests in the same package when changing behavior; follow table-driven style if the package already does.

## Dependencies

Declared in `**src/go.mod**` / `**src/go.sum**`. After new imports, run `**go mod tidy**` inside `**src/**`.

## Contributing

1. Use this file plus `**README.md**` and `**docs/OPERATIONS.md**` for context.
2. Run `**go test ./...**` from `**src/**` before proposing a merge.
3. Record subtle integration or migration notes under `**docs/solutions/**` when the task calls for it.

---

## Project profile

**Replace this block when you copy `AGENTS.md` to another repo.**


| Field                        | This repo (WaShield)                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| **Name**                     | WaShield — WhatsApp group link shortener with geo-blocking, honeypot, dashboard     |
| **Primary language / stack** | Go (module root: `src/`), SQLite, server-rendered web UI, Clerk auth, Polar billing |
| **Build / test**             | From `src/`: `go build ./cmd/server`, `go test ./...`                               |
| **Entry point**              | `src/cmd/server/main.go`                                                            |
| **Config**                   | `.env.example`, `README.md` environment tables                                      |
| **Operational notes**        | `docs/OPERATIONS.md` (migrations, backfill, hosting)                                |
| **Institutional knowledge**  | `docs/solutions/` (patterns, integrations, incident notes)                          |


---

## What you should do

1. **Orient** — Read `README.md` and skim `docs/OPERATIONS.md` if the task touches deployment, auth, billing, or data migration.
2. **Locate code** — Find real entry points and callers before editing; prefer extending existing patterns over new abstractions.
3. **Scope** — Change only what the task requires. Do not commit build artifacts, local databases, secrets, or editor cache directories.
4. **Verify** — Run the project’s tests and any relevant build command from the correct directory (here: `src/` for Go).
5. **Document gaps** — If you discover a non-obvious constraint, add or update a short note under `docs/` only when that is part of the task.

---

## Repository conventions (WaShield)

- **Go module** lives under `src/`; import paths and `go test ./...` assume that working directory.
- **Auth** — Clerk JWT validation and webhooks; user identity for API scoping is the JWT `sub` (see link `owner_user_id` and billing `external_customer_id` patterns).
- **Billing** — Polar integration under `src/internal/billing/`; feature-flag benefit metadata merges with defaults in code (see `docs/solutions/best-practices/polar-sh-washield-billing-entitlements-2026-04-22.md`).
- **Web** — Handlers and templates under `src/internal/web/`; keep server-side enforcement aligned with what the UI suggests.

When copying this file to **another** project, replace the bullets above with that repo’s real layout and rules.

---

## MCP integration (portable)

[Model Context Protocol](https://modelcontextprotocol.io/) exposes external capabilities as **tools** and **resources** the agent can call. Configure servers in the **editor or CLI** that hosts the agent (for example Cursor’s MCP settings, or Claude Code’s [MCP docs](https://docs.claude.com/en/docs/claude-code/mcp) and plugin `.mcp.json`). This repo does **not** need to implement MCP in application code for editor tooling.

### Transport types (pick one per server)


| Type      | Typical use                                                         | Auth / config                                       |
| --------- | ------------------------------------------------------------------- | --------------------------------------------------- |
| **stdio** | Local process (`command` + `args`) — custom servers, `npx` packages | Environment variables, no secrets in committed JSON |
| **sse**   | Hosted URL (`type: sse`, `url`) — vendor MCP endpoints              | Often OAuth; follow host instructions               |
| **http**  | REST MCP (`type: http`, `url`, `headers`)                           | Bearer or API keys via `${ENV_VAR}`                 |
| **ws**    | WebSocket (`type: ws`)                                              | Tokens in headers                                   |


Use **HTTPS** / **WSS** for remote URLs. Prefer **environment variable substitution** for tokens and paths so the same config works across machines.

### Security and hygiene

- Do **not** commit API keys, bearer tokens, or `.env` into git. Document required variables in `README.md` or `.env.example` only as **names**, not values.
- After changing MCP config, **restart** the editor session or MCP connection if tools do not appear.
- Prefer **narrow** tool access in automation (allow lists in commands/agents) over wildcards when your host supports it.
- If a tool call fails, check connectivity, auth, and rate limits before retrying in a loop.

### What agents should do with MCP

1. **Discover** — Use the host’s MCP UI or tool descriptors to see exact tool names and parameters.
2. **Validate** — Match argument types and required fields before calling.
3. **Fallback** — If the server is offline, continue with repo search, tests, and logs.

---

## Context Broker MCP (`user-context-broker`)

Enable the **Context Broker** MCP server for this workspace. In Cursor, the server identifier is `**user-context-broker`** (it may display as **context-broker**). Use it to **bootstrap understanding** and run **semantic search** over the codebase, especially early in a task or when file paths are unknown.

### When to use it

- **Unfamiliar area** — `auto_search` (optional `project_root`) for entry points and configuration.
- **Semantic lookup** — `search_codebase_tool` with a natural-language `query` (optional `project_root`).
- **Persisted investigation** — `save_search_results` writes JSON snapshots; `list_saved_results` / `load_saved_results` need `project_name` (and `filename` for load).
- **Storage** — `get_storage_config` shows where saved results are stored.
- **Token usage** — `token_counter` (optional `project_root`) for editor-oriented usage reporting.

### Resources

- `codebase://auto-context` — Auto-provided codebase context.
- `codebase://token-counter` — Latest token counter for dashboards.

Always read the MCP tool schema in your environment’s MCP descriptor if a parameter is unclear. Prefer Context Broker **once** for orientation, then confirm with normal search, tests, and stack traces.

---

## Copy checklist (new project)

1. Copy this `AGENTS.md` to the **git root** of the new project.
2. Update the [Project profile](#project-profile) table and the **Repository conventions** section.
3. Register MCP servers in the host (Cursor / Claude Code / other): enable **Context Broker** as `**user-context-broker`**, and add any other project-specific servers. Document required **environment variables** beside the server name in the profile table or `README.md`.
4. If the project uses a monorepo or non-root module path, state the **exact directory** for install, build, and test commands.

