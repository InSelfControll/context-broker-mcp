# Changelog

All notable changes to the Context Broker MCP Server project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased] — 2026-09-05

### Added

- Support Relayhelm as a native integration host with its own config destination and shared project-bound MCP transport.

- Add explicit Index / No index choice for project history; both modes retrieve only issue-relevant excerpts, with bounded scans and no automatic full-memory preload.
- Check local issue history automatically on question-bearing routing/search calls and document the standalone provider/Cursor/messaging harness design.

- Add immutable cross-model project handoffs preserving exact supplied memory, task failures, decisions, evidence, and file snapshots; reject stale, corrupt, secret-bearing, or oversized context without silent truncation.

- Generate project-bound MCP configuration fragments for Codex, Hermes, Cursor, and Claude Code with native configuration keys and timeout units.

- Add consent-gated `delegate_large_task`: 2–4 parallel model-pinned proposal workers, shared project context, and an acceptance-criteria integration review; no workers start if the user declines or elicitation is unavailable.
- Bound delegation inputs, outputs, concurrency, and provider timeouts; reject model substitution, stale context, and incomplete handoffs without silently truncating context or applying unverified changes.

- Add opt-in authenticated local `serve` / project-bound stdio `connect` commands so coding agents can share one model and memory pool across sessions.
- Add aggregate shared-process cache diagnostics through `get_memory_usage`.

### Changed

- Bound retained index/query/report caches in one LRU pool; lazy-load ML imports and serialize model initialization and inference.
- Stream index encoding in batches, memory-map cached vectors, compute cosine similarity in chunks, and invalidate indexes on corpus changes.
- Move blocking search, storage, routing, and context operations into bounded workers with request-local project identity.
- Separate global storage for equally named projects in shared mode; preserve existing standalone storage paths.

### Fixed

- Make CLI help and invalid commands exit without starting a server; expose command help through MCP prompts and resources.

- Return explicit failed task records with reasons and MCP error flags; reject agent-declared failures and failed integration reviews while retaining successful handoffs.
- Use stateful shared MCP sessions so interactive task-splitting consent reaches stdio clients instead of timing out.

- Evaluate ignored directories relative to the project, so projects located under `tmp` or `temp` remain searchable.
- Lock disk index cache operations and keep the build fingerprint when publishing cached vectors.

- Stop a busy Linux stdio broker when its client closes the MCP pipe, even if the editor stays open.
- Keep downstream MCP sessions in a dedicated owner task so SDK cancellation scopes close correctly; reuse ready connections, clear stale discovery, validate retry limits, and enforce operation timeouts without replaying tool calls.
- Honor advertised downstream capabilities and collect all discovery pages; remove tools deleted by downstream servers from registry caches.
- Cancel idle WebSocket transport workers on exit and move blocking dashboard backend reads off the ASGI event loop.
- Reject storage path traversal and symlink escapes; preserve previous JSON saves when serialization fails and list global fallback saves in in-project mode.
- Lock chat ledger read/append/write operations across processes, use unique atomic temporary files, and refuse to overwrite corrupt ledgers.
- Scan all returned source content for secret signatures and redact sensitive dictionary values by key.
- Enforce router token and tool limits, isolate cached responses from caller mutation, and bound plan cache growth with `CONTEXT_BROKER_ROUTER_PLAN_CACHE_MAX_ENTRIES`.
- Close registry SQLite and Redis clients and bound optional Redis connection/read waits.
- Update the Transformers dependency chain to address CVE-2026-9856; share JSON persistence and context identifier helpers across consumers.

- 🐛 **search_context / indexing timeouts**: stop recursive `glob` walks that followed project `result` → `/nix/store` (and other symlink escapes), which routinely exceeded the client 300s MCP tool budget on Nix/HM trees. File collection now uses a single `os.walk` that prunes ignored dirs up front and refuses symlink descent by default (`CONTEXT_BROKER_INDEX_FOLLOW_SYMLINKS=0`).
- 🐛 allow MCP harnesses to disable automatic `.env` loading
- 🐛 limit bootstrap to model cache misses — `13aa679`
- 🐛 bootstrap missing embedding models — `4814a9f`

### Added

- ✨ On-disk corpus embedding cache under `.cache/context-broker-index.{json,npy}` so idle cleanup / process restarts reload embeddings without a full re-encode (`CONTEXT_BROKER_INDEX_DISK_CACHE=1`).
- ✨ Index collection guards: `CONTEXT_BROKER_INDEX_MAX_FILE_BYTES` (default 2MB), hard-ignore Nix `result*` product dirs, index `*.nix` and `*.yml`.
- ✨ Shared `collect_project_files` used by semantic index + literal search.
- ✨ Hard-ignore bulky non-source artifacts via `DEFAULT_IGNORE_FILE_PATTERNS` (case-insensitive): `*.iso`, VM disks (`*.qcow2`/`*.vmdk`/…), archives, packages, media, dumps — e.g. `ofir-nixos-kde-installer.iso`.

### Documentation

- 📝 record model bootstrap refinement — `a5f6a00`
- 📝 update changelog — `4493a54`
- 📝 explain embedding model bootstrap — `daf2d21`
- 📝 plan automatic model bootstrap — `c42c60f`
- 📝 specify automatic model bootstrap — `3e960ac`

## [Unreleased] — 2026-07-05

### Added

- ✨ Downstream MCP client subsystem for Universal Context Router Phase 1: stdio, streamable HTTP, and SSE transports; connection manager; reconnect; heartbeat; capability discovery; and downstream tool calls.
- ✨ Universal Context Router runtime foundations for Phases 2-7: expanded tool registry metadata, SQLite/optional Redis registry cache, downstream descriptor ingestion, intent/decomposition routing, DAG stages, opt-in minimal public surface, safety-gated `execute_plan`, secret redaction, route metrics, and router benchmark tool.
- ✨ Redis cross-chat context backend, web dashboard, chat ledger, and user activity tracking — `40848bd`

### Fixed

- 🐛 dashboard message timestamps, recency sort, no-store cache, atomic SET ex — `fb181fb`

### Documentation

- 📝 Add `ARCHITECTURE_MIGRATION.md` and update README/architecture docs with Universal Context Router migration status.
- 📝 Add Universal Context Router RFC series covering vision, architecture, registry, routing, decomposition, planning, compression, exposure, execution, adapters, security, plugins, storage, observability, benchmarks, APIs, testing, deployment, and roadmap.
- 📝 add AGENTS.md with MCP config, cursor rules, and project structure — `d75d588`
- 📝 fix CHANGELOG versioning, add AGENTS.md config example with cursor rules — `7179a6c`

### Chore

- 🔧 update uv.lock after pyproject.toml changes — `4a9f702`
- 🔧 bump urllib3 from 2.6.3 to 2.7.0 (#17) ([#17](https://github.com/yourusername/context-broker-mcp/pull/17)) — `c9d13b5`
- 🔧 bump authlib from 1.6.9 to 1.6.12 (#18) ([#18](https://github.com/yourusername/context-broker-mcp/pull/18)) — `2bde8fb`

### Uncategorized

- 📝 Merge pull request #19 from InSelfControll/cursor/token-savings-history ([#19](https://github.com/yourusername/context-broker-mcp/pull/19)) — `5598638`
- 📝 Create AGENTS.md for project agent instructions — `45bf942`
- 📝 Merge pull request #15 from InSelfControll/cursor/token-savings-history ([#15](https://github.com/yourusername/context-broker-mcp/pull/15)) — `27d5f32`
- 📝 Merge pull request #14 from InSelfControll/cursor/token-savings-history ([#14](https://github.com/yourusername/context-broker-mcp/pull/14)) — `8278305`

## [0.3.0] — 2026-05-14

### Added

- ✨ Per-user activity audit in Redis. On every save, the broker now SADDs the speaker into `<prefix>:ctx:project:<digest>:users`, bumps `first_seen` / `last_seen` / `request_count` in a per-user HASH, and appends `{timestamp, session_id}` to a per-user LIST. New MCP tool `list_user_activity(project_root, peer_id?, limit?)` returns either the per-user summary or a single user's full request log. New dashboard routes `/projects/{digest}/users` and `/projects/{digest}/users/{peer_id}` plus JSON twins under `/api/`. Answers "when did this user last ask something?" without scanning every session.
- ✨ Default-on warm-on-save (`CONTEXT_BROKER_AUTO_WARM_CACHE_ON_SAVE=1`). Every `save_chat_context` / `record_turn` / `record_session` now invalidates all prior cache entries for the session AND immediately warms the default-params signature with the freshly persisted session. A `load_chat_context` right after a save is a cached hit, not a miss-then-fill round trip. Save responses include `cache_warmed: true|false`.
- ✨ `record_session` MCP tool — bulk-persist an entire conversation in one call via `turns: [{user, assistant}, ...]`. Each turn is appended (no overwrites), mirrored to the JSON ledger, and the cache is warmed once at the end. Use when you have the full conversation in context (e.g. "save the whole chat") instead of firing N `record_turn` calls.
- ✨ Local-JSON chat ledger: every `save_chat_context` / `record_turn` is dual-written to `<storage>/chats/<project_digest>/<session_id>.json` (atomic temp-rename, append-only). Chat history now survives Redis wipes or Honcho outages and is human-readable on disk. Save responses include `ledger_files: [...]`.
- ✨ `record_turn` MCP tool — thin convenience wrapper over `save_chat_context` with a docstring engineered to make LLM clients auto-invoke it after every response so chat history accumulates per session without manual prompting.
- ✨ `load_cross_session_context` MCP tool — scans every session of a project, filters by `search_query` (substring, case-insensitive), and returns the top-N matches across sessions sorted by recency with `session_id` attribution. Requires the Redis backend.
- ✨ Opt-in user-identity resolver (`CONTEXT_BROKER_USE_ACCOUNT_NAME=1` plus optional `CONTEXT_BROKER_ACCOUNT_NAME_OVERRIDE`). Saved/loaded chats record the questioner under the OS account name (e.g. `ofir`) instead of the generic `user`, so the dashboard shows who actually asked. Explicit `user_peer_id` args from MCP callers still win; assistant peer id is untouched. Surfaced in `context_backend_status.identity` and `get_storage_config`.
- ✨ `.env` auto-loading for the MCP server and dashboard entrypoints. Walks up from CWD, never overrides parent env. Lets a single `.env` feed every editor's MCP client (Claude Code, Codex, Cursor, …).
- ✨ Dashboard single-instance guard. Re-launching `python -m context_broker dashboard` when one is already running probes `/api/status`, recognises the existing instance, and exits 0 instead of failing with port-in-use.
- ✨ Redis-backed chat-payload cache (`CONTEXT_BROKER_CHAT_CACHE_TTL_SECONDS`, default 300). `load_chat_context` is served from Redis with TTL — works for both Honcho and Redis context backends. Save invalidates the per-session entries. Cache hits include `"cached": true` in the payload.
- ✨ Redis-backed cross-chat context backend (`CONTEXT_BROKER_CONTEXT_BACKEND=redis`) mirroring Honcho's `save_chat_context` / `load_chat_context` API. Messages are stored under `<prefix>:ctx:project:<digest>:session:<id>` so chats survive across sessions.
- ✨ Web-only cross-chat dashboard (`python -m context_broker dashboard` or `context-broker-dashboard`) built on Starlette. Browses projects → sessions → messages stored by the Redis backend. JSON API mirrors the HTML routes.
- ✨ `context-broker-dashboard` console script registered as a project entry point alongside the existing `context-broker` MCP server.
- ✨ Dashboard host/port env vars: `CONTEXT_BROKER_DASHBOARD_HOST` (default `127.0.0.1`) and `CONTEXT_BROKER_DASHBOARD_PORT` (default `8770`).
- ✨ `context_backend_status` MCP tool — reports the configured cross-chat backend (`honcho` / `redis` / `disabled`), connection health, and the resolved identity profile in one call. Useful for editors that want to surface backend status without scraping `get_storage_config`.
- ✨ Optional install extras: `context-broker[dashboard]` (Starlette + uvicorn + Jinja2 + python-dotenv) and `context-broker[integrations]` (honcho-ai + redis client) so cross-chat support is opt-in rather than a hard dependency.
- 🧪 Comprehensive integration test suite (`tests/test_integrations.py`, ~1.2k lines) exercising both Honcho and Redis context backends, the chat ledger, the chat-payload cache, identity resolution, dashboard data tasks, and `record_turn` / `record_session` flows end-to-end.

### Removed

- 🔥 Redis **query-cache** backend (the prior caching role); query cache is local-JSON only. Redis remains supported, but only as the cross-chat context backend described above.

### Fixed

- 🐛 Dashboard double-launch no longer crashes with `OSError: [Errno 98] Address already in use`. The new single-instance guard probes `/api/status` first and exits 0 when an existing dashboard is already serving on the configured host/port.
- 🐛 `load_chat_context` immediately following a `save_chat_context` no longer returns a stale-empty payload from the cache layer; saves now invalidate prior cache entries and warm the default-params signature in the same call.
- 🐛 MCP server no longer overrides parent-process environment variables when auto-loading `.env`; the walker stops at the first match and only sets keys that aren't already in `os.environ`.

## [0.2.0] — 2026-05-01

### Added

- ✨ optional Honcho cross-chat context tools
- ✨ track token savings history — `4d05994`
- ✨ configurable embedding model (`CONTEXT_BROKER_EMBEDDING_MODEL`), device (`CONTEXT_BROKER_DEVICE`), and optional LLM env vars (`CONTEXT_BROKER_LLM_MODEL`, `CONTEXT_BROKER_LLM_BASE_URL`, `CONTEXT_BROKER_LLM_API_KEY`) — `63d7d8f`
- ✨ automated feature documentation generation — `a5f9c4b`
- ✨ automated CHANGELOG.md generation from git commits — `4bef4ef`
- ✨ AGENTS.md auto-generation, lifecycle watchdogs, and resource management — `97a4054`
- ✨ add async tool support with progress notifications and logging — `8c75a18`
- ✨ initial release of Context Broker MCP server — `64a5a23`

### Fixed

- 🐛 include token efficiency report in MCP tool responses — `53f310e`

### Security

- 🔒 refine .npmrc/.yarnrc handling — content-based only — `ab98f44`
- 🔒 add defense-in-depth secret file protection — `350c432`

### Changed

- ♻️ migrate to TTC modular architecture — `5410ea2`

### Documentation

- 📝 add comprehensive run commands and MCP client configuration — `d9bc0bb`

### Chore

- 🔧 bump fastmcp from 3.1.1 to 3.2.0 — `38e678f`
- 🔧 bump pygments from 2.19.2 to 2.20.0 — `b3558cc`
- 🔧 bump cryptography from 46.0.5 to 46.0.6 — `4859095`
- 🔧 bump requests from 2.32.5 to 2.33.0 — `745f25c`
- 🔧 bump minimum dependency versions in pyproject.toml — `527ea5e`
- 🔧 upgrade dependencies to latest versions — `81f0559`
- 🔧 update fastmcp dependency to v3 beta — `4b6d32e`

### Uncategorized

- 📝 Merge pull request #8 from InSelfControll/dependabot/uv/pygments-2.20.0 ([#8](https://github.com/yourusername/context-broker-mcp/pull/8)) — `3f388df`
- 📝 Merge pull request #6 from InSelfControll/dependabot/uv/requests-2.33.0 ([#6](https://github.com/yourusername/context-broker-mcp/pull/6)) — `20cdeb2`
- 📝 Merge pull request #7 from InSelfControll/dependabot/uv/cryptography-46.0.6 ([#7](https://github.com/yourusername/context-broker-mcp/pull/7)) — `effc6ba`
- 📝 Merge pull request #9 from InSelfControll/dependabot/uv/fastmcp-3.2.0 ([#9](https://github.com/yourusername/context-broker-mcp/pull/9)) — `630191d`
- 📝 Update README.md — `bba8ad3`

### AGENTS.md Management Suite

- **New MCP Tools** for automated AGENTS.md lifecycle management:
  - `ensure_agents_md_tool` — Creates AGENTS.md automatically if missing, preserving existing files.
  - `validate_agents_md_tool` — Validates existing AGENTS.md and reports missing sections with a quality score (0–100).
  - `generate_agents_md_tool` — Force-regenerates AGENTS.md from project metadata (useful for onboarding or refreshes).
  - `scan_projects_for_agents_md` — Recursively scans subdirectories for projects missing AGENTS.md, using project markers (`.git`, `package.json`, `pyproject.toml`, etc.).
- **Intelligent Project Detection**: Extracts metadata from common project files:
  - `package.json` → Node.js projects (name, version, description, dependencies, entry points)
  - `pyproject.toml` → Python projects (name, version, description, dependencies)
  - `Cargo.toml` → Rust projects (name, version, description)
  - `go.mod` → Go projects (module name)
  - `pom.xml` / `build.gradle` → Java projects (Maven/Gradle)
  - `requirements.txt` → Python dependencies
  - `README.md` → Project description extraction
  - `Dockerfile`, `Makefile` → Build tooling detection
  - `LICENSE` → License detection
- **Validation Engine**: Scores AGENTS.md quality by checking:
  - **Required sections**: Project Goals / Purpose / Overview / Description / Objectives / Mission
  - **Optional sections**: Tech Stack, Architecture, Testing, Deployment, Contributing, Dependencies, Project Structure
  - Provides actionable suggestions when sections are missing
- **Generated Template Structure**: Every generated AGENTS.md includes:
  - Project Goals (core purpose)
  - Overview (name, version, license)
  - Tech Stack (auto-detected)
  - Entry Points (auto-detected)
  - Key Dependencies (top 15, auto-detected)
  - Architecture & Conventions (placeholder for team input)
  - Testing (placeholder for team input)
  - Deployment (placeholder for team input)
- **New TTC Module**: `agents_ttc/` following the established TTC (Task-Tool-Codebase) architecture:
  - `agents_ttc/tools/agents_tools.py` — Core helpers (detection, reading, writing, metadata extraction, content generation, validation)
  - `agents_ttc/tasks/agents_tasks.py` — High-level orchestration (ensure, validate, generate, scan)
  - `agents_ttc/codebase/api.py` — Public API surface
  - `agents.py` — Backward-compatible wrapper module
- **Server Integration**: Registered in `server_ttc/codebase/assembly.py` alongside existing search, storage, and token tools.
- **Test Coverage**: 19 comprehensive tests covering:
  - AGENTS.md presence detection (case-insensitive)
  - Metadata extraction for empty, README-backed, Node.js, and Python projects
  - Content generation validation
  - Validation scoring (missing, valid, needs-work)
  - Task-level flows (create, overwrite, no-force, scan)

### Process Lifecycle & Resource Management

- **`context_broker/lifecycle.py`**: New module providing production-grade process lifecycle management:
  - **Parent Death Detection**: Automatically exits the MCP server when its launching editor/host process disappears (prevents orphaned processes).
  - **Idle Resource Cleanup**: Releases in-memory model/index caches after prolonged idle periods to prevent RAM bloat.
  - **Startup Ancestor Tracking**: Tracks the process chain at startup for reliable orphan detection.
  - **Background Watchdog Threads**: Daemon threads monitor parent health and idle timeouts concurrently without blocking MCP operations.
- **`start_lifecycle_watchdogs()`**: Integrated into `__main__.py` so watchdogs start automatically on server boot.
- **New Environment Variables** (all configurable):
  - `CONTEXT_BROKER_EXIT_WHEN_PARENT_DIES` — Enable parent-death detection (default: `1`)
  - `CONTEXT_BROKER_PARENT_POLL_INTERVAL_SECONDS` — Parent health poll interval (default: `3`)
  - `CONTEXT_BROKER_IDLE_RESOURCE_TIMEOUT_SECONDS` — Idle cache release timeout, `0` disables (default: `900`)
  - `CONTEXT_BROKER_IDLE_RESOURCE_CLEANUP_INTERVAL_SECONDS` — Idle cleanup check interval (default: `30`)

### Configuration Improvements

- **`config.py`**: Added safe env-var parsing helpers:
  - `_get_env_int(name, default)` — Parses integer env vars with fallback
  - `_get_env_float(name, default)` — Parses float env vars with fallback
- `MODEL_LOCAL_ONLY` now forces offline mode for HuggingFace and Transformers by setting `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.
- `WORKER_CORES` automatically limits PyTorch, NumPy, and MKL thread pools to prevent CPU over-subscription.

### Modular Architecture Refinements

- **`server_ttc/codebase/assembly.py`**: Added `register_agents_tools()` to the MCP server initialization pipeline.
- **`server_ttc/codebase/resources.py`**: Refactored resource and prompt registration for consistency with the TTC pattern.
- **Various TTC modules**: Applied minor formatting and consistency improvements across `indexer_ttc`, `project_ttc`, `storage_ttc`, and `server_ttc` packages.

### Resource Leak Fixes

- **In-memory indexes, query caches, token reports, and model encoders** are now properly released during idle cleanup and process shutdown.
- **Orphaned processes**: MCP server no longer lingers indefinitely when the AI editor (Claude Desktop, etc.) is closed.

### Secret File Protection (Defense-in-Depth)

- **Hard-coded secret file patterns** (`SECRET_FILE_PATTERNS`) that CANNOT be overridden by `.gitignore` or user configuration:
  - Environment files: `.env`, `.env.*`, `*.env`, `*.env.*`
  - AWS credentials: `.aws/credentials`, `.aws/config`
  - SSH / TLS keys: `id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519`, `*.pem`, `*.key`, `*.p12`, `*.pfx`
  - Kubernetes: `*.kubeconfig`, `kubeconfig`
  - Docker registry: `.docker/config.json`
  - NPM / Yarn auth: `.npmrc`, `.yarnrc`
  - Pip auth: `.pypirc`
  - Git credentials: `.git-credentials`
  - Terraform state: `*.tfstate`, `*.tfstate.*`
  - Database dumps: `*.dump`, `*.sql.dump`
  - Known secret filenames: `secrets.*`, `secret.*`, `*.secrets`, `*.secret`, `credentials.*`, `*.credentials`, `*.token`, `*.tokens`, `api_key*`, `apikey*`, `private_key*`, `privatekey*`
- **Content-based secret detection** (`SECRET_ENV_KEY_PATTERNS`) that scans file contents for secret signatures:
  - `PRIVATE_KEY`, `SECRET_KEY`, `API_KEY`, `ACCESS_KEY`, `AUTH_TOKEN`, `PASSWORD`, `SECRET`, `CREDENTIAL`
  - `TOKEN=`, `KEY=`, `SECRET=`, `PASSWORD=`
  - Catches renamed `.env` files and other secret-bearing files that don't match filename patterns
  - Prefers longer/more specific patterns (e.g., `API_KEY` before `KEY=`)
  - Skips comment lines (`# ...`) to avoid false positives
  - Only scans first 100 lines for performance
- **Three-layer defense architecture**:
  1. **Indexing layer**: `should_ignore()` hard-blocks secret files before they enter the index
  2. **I/O layer**: `read_file_content()` performs content scanning and returns `None` for secret files
  3. **Search layer**: Search results only come from the already-filtered index
- **Security audit logging**: Every blocked file emits a `🔒 SECURITY` log with operation type (`index`, `read`, `search`) and reason for blocking
- **Security configuration summary**: `get_security_summary()` reports pattern counts for transparency
- **New `security_ttc/` module** following TTC architecture:
  - `security_ttc/tools.py` — Pattern matching, content scanning, audit logging
- **35 security tests** covering:
  - Filename pattern matching (13 tests)
  - Content signature detection (7 tests)
  - Combined `is_secret_file()` logic (4 tests)
  - `should_ignore()` integration (4 tests)
  - `read_file_content()` blocking (5 tests)
  - Configuration and audit logging (2 tests)

---

## [0.1.0] — 2026-04-28

### Added

- Semantic code search using sentence transformers (`all-MiniLM-L6-v2`)
- MCP protocol server with `stdio`, `sse`, `streamable-http`, and `ws` transports
- Auto project root detection via marker scoring (`.git`, `pyproject.toml`, `package.json`, etc.)
- Smart caching with file-modification tracking
- Token efficiency reporting for every query
- Persistent search results storage (global, in-project, or both modes)
- `.gitignore` and `.dockerignore` respect
- Modular TTC (Task-Tool-Codebase) architecture
- Progress notifications and rich logging
