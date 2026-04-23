# Changelog

All notable changes to the Context Broker MCP Server project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

#### AGENTS.md Management Suite
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

#### Process Lifecycle & Resource Management
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

#### Configuration Improvements
- **`config.py`**: Added safe env-var parsing helpers:
  - `_get_env_int(name, default)` — Parses integer env vars with fallback
  - `_get_env_float(name, default)` — Parses float env vars with fallback
- `MODEL_LOCAL_ONLY` now forces offline mode for HuggingFace and Transformers by setting `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.
- `WORKER_CORES` automatically limits PyTorch, NumPy, and MKL thread pools to prevent CPU over-subscription.

### Changed

#### Modular Architecture Refinements
- **`server_ttc/codebase/assembly.py`**: Added `register_agents_tools()` to the MCP server initialization pipeline.
- **`server_ttc/codebase/resources.py`**: Refactored resource and prompt registration for consistency with the TTC pattern.
- **Various TTC modules**: Applied minor formatting and consistency improvements across `indexer_ttc`, `project_ttc`, `storage_ttc`, and `server_ttc` packages.

#### Documentation
- **`README.md`**: Documented all new lifecycle environment variables and their defaults.

### Fixed

- **Resource leaks**: In-memory indexes, query caches, token reports, and model encoders are now properly released during idle cleanup and process shutdown.
- **Orphaned processes**: MCP server no longer lingers indefinitely when the AI editor (Claude Desktop, etc.) is closed.

---

## [0.1.0] – Previous Release

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

---

## What We've Achieved So Far

1. **Production-Ready MCP Server**: Context Broker is a fully functional semantic code search server that integrates with Claude Desktop, Cursor, and any MCP-compatible client.

2. **Autonomous Project Onboarding**: The new AGENTS.md management suite enables AI assistants to automatically discover project context, generate onboarding documentation, and validate that existing documentation is complete — all through MCP tool calls.

3. **Resource-Safe Operations**: With lifecycle watchdogs, the server cleans up after itself. It won't leak RAM from embedding models or leave zombie processes when editors close.

4. **Cross-Platform Project Intelligence**: Automatic detection of Python, Node.js, Rust, Go, Java, Docker, and generic projects means the AGENTS.md generator works out of the box for any codebase.

5. **Quality Gates**: The validation engine ensures AGENTS.md files contain meaningful project goals and conventions — not just boilerplate.

6. **Extensible Architecture**: The TTC pattern makes it trivial to add new tool categories. The agents module followed the same blueprint as search, storage, and token modules.
