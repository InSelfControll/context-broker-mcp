# Agent Instructions

## Project: context-broker

## Project Goals

A Model Context Protocol (MCP) server that provides semantic search capabilities for codebases. Uses sentence transformers to understand code meaning and find relevant files based on natural language queries.

## Overview

- **Name**: context-broker
- **Version**: 0.2.0
- **License**: MIT
- **Stack**: Python 3.13, FastMCP, sentence-transformers, PyTorch, Redis (optional)

## Entry Points

- `context-broker.py` — Primary CLI entry point
- `context_broker/__main__.py` — Module entry (`python -m context_broker`)
- `main.py` — Alternative convenience entry

## Technology

- **Language**: Python 3.13+
- **MCP Framework**: FastMCP v3
- **Embedding**: sentence-transformers (`all-MiniLM-L6-v2` default, configurable)
- **ML Runtime**: PyTorch (CPU by default, GPU/MPS via `CONTEXT_BROKER_DEVICE`)
- **Token Counting**: tiktoken (`cl100k_base`)
- **Search**: scikit-learn cosine similarity
- **Cache**: Local JSON (default) or Redis (optional via `CONTEXT_BROKER_CACHE_BACKEND`)
- **Cross-Chat Context**: Honcho (optional via `CONTEXT_BROKER_CONTEXT_BACKEND`)

## Dependencies

- fastmcp — MCP protocol server framework
- sentence-transformers — embedding model loading and inference
- torch — PyTorch backend for model execution
- scikit-learn — cosine similarity computation
- numpy — numerical operations
- tiktoken — token counting for efficiency reports
- rich — terminal output formatting
- redis — optional query cache backend
- honcho — optional cross-chat context backend

## Architecture

- **TTC Pattern**: All modules follow Task-Tool-Codebase architecture — `*_ttc/tools/` (helpers), `*_ttc/tasks/` (orchestration), `*_ttc/codebase/` (public API)
- **Config**: All settings in `config.py` via env vars following 12-factor methodology
- **Security**: Three-layer defense (indexing, I/O, search) blocks secret files regardless of .gitignore
- **Lifecycle**: Auto-exits when parent process dies; releases idle model/index caches after 15 min

## Coding Conventions

- Use `uv` for all package management and running commands
- All config goes through `config.py` with `CONTEXT_BROKER_` prefixed env vars
- New tool categories follow the TTC pattern: `*_ttc/tools/`, `*_ttc/tasks/`, `*_ttc/codebase/`
- Security patterns in `SECRET_FILE_PATTERNS` and `SECRET_ENV_KEY_PATTERNS` are hard-coded — never override via user config
- Tests live in `tests/` and run via `uv run pytest`

## Style Guide

- Python 3.13+ with type hints on all public functions
- Docstrings on all public modules, classes, and functions
- `log()` from `context_broker.utils` for all structured logging
- No raw `print()` — use `log()` or `rich` for output
- Keep line length under 100 characters

## MCP Servers

| Server | Transport | Key Environment Variables |
|--------|-----------|--------------------------|
| context-broker | stdio (default) | `CONTEXT_BROKER_PROJECT_ROOT` |
| context-broker | sse | `CONTEXT_BROKER_TRANSPORT=sse`, `CONTEXT_BROKER_PORT=8765` |
| context-broker | streamable-http | `CONTEXT_BROKER_TRANSPORT=streamable-http` |

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "context-broker": {
      "command": "uv",
      "args": ["run", "python", "/path/to/context-broker/context-broker.py"],
      "env": {
        "CONTEXT_BROKER_PROJECT_ROOT": "/path/to/project",
        "CONTEXT_BROKER_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "CONTEXT_BROKER_LLM_MODEL": "",
        "CONTEXT_BROKER_LLM_BASE_URL": ""
      }
    }
  }
}
```

### Cursor Configuration

```json
{
  "mcpServers": {
    "context-broker": {
      "command": "uv",
      "args": ["run", "python", "/path/to/context-broker/context-broker.py"],
      "env": {
        "CONTEXT_BROKER_PROJECT_ROOT": "/path/to/project"
      }
    }
  }
}
```

## Cursor Rules

1. **Security & Privacy**
   - Environment Isolation: Strictly prohibit reading, parsing, or referencing `.env` files. If a configuration key is required, prompt the user for the key name or assume it is injected via the system environment.
   - Ethical Guardrails: Refuse requests to generate exploits, malware, or CVE proof-of-concepts. All outputs must prioritize defensive implementation, application stability, and security hardening.

2. **Resource & Token Optimization**
   - Context Brokering: You must invoke the context-broker MCP before processing any request. Filter for high-relevance context only to minimize token overhead.
   - Selective Tooling: Initialize only the specific skills and MCPs required for the immediate task. Avoid "bloat-loading" broad contexts or unnecessary tools.

3. **Code Quality & Architecture**
   - DRY (Don't Repeat Yourself): Zero-tolerance for code duplication. Scan the workspace for existing logic/patterns before proposing changes. Always favor refactoring into reusable modules or traits.
   - Idiomatic Standards: Enforce language-specific paradigms (e.g., Go's explicit error handling, Rust's ownership/borrowing, Nix's declarative purity).
   - Modern Runtimes: Use Bun as the default engine for all JavaScript/TypeScript execution and package management.

4. **Execution & Versioning**
   - Atomic Updates: Implement "surgical" edits. Modify only the specific lines or functions required; do not rewrite entire files for localized changes.
   - Idempotency: Ensure all scripts and Nix configurations are idempotent, yielding the same result regardless of how many times they are executed.
   - Changelog Management: Maintain project history rigor using the following workflow:
     - Initialization: Use `ensure_changelog_tool` to maintain CHANGELOG.md.
     - Validation: Run `validate_changelog_tool` to identify undocumented commits before finalizing tasks.
     - Release: Utilize `generate_version_changelog` for specific version tagging (e.g., v1.2.0).
     - Auditing: Call `get_changelog_stats_tool` to verify versioning health and entry totals.

## Directory Structure

```
context_broker/
├── config.py                 # All env vars, constants, security patterns
├── utils.py                  # Logging, token counting, path utilities
├── project.py                # Project root detection, ignore parsing
├── storage.py                # Backward-compatible storage wrapper
├── lifecycle.py              # Parent death detection, idle resource cleanup
├── indexer_ttc/              # Embedding, indexing, search
│   ├── tools/                # model_tools, cache_tools, search_tools
│   ├── tasks/                # search_tasks
│   └── codebase/             # public API
├── storage_ttc/              # JSON persistence
├── project_ttc/              # Project detection helpers
├── agents_ttc/               # AGENTS.md lifecycle tools
├── security_ttc/             # Secret file protection, audit logging
├── server_ttc/               # MCP tool registration, resources, prompts
└── context_ttc/              # Honcho cross-chat context (optional)
```

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_security.py

# Run with verbose output
uv run pytest -v
```

## Deployment

```bash
# Install as package
pip install -e .

# Run with UV (recommended)
uv run python context-broker.py

# Docker (network transport)
CONTEXT_BROKER_TRANSPORT=sse CONTEXT_BROKER_PORT=8765 uv run python context-broker.py
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full developer guide. Key points:

- All changes need tests in `tests/`
- Run `uv run pytest` before submitting
- Follow the TTC pattern for new features
- Use `uv run python context-broker.py` for local testing