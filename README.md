<div align="center">

# 🔍 Context Broker MCP

**Give your AI agent a photographic memory of your codebase.**

Semantic search + persistent cross-chat context for Claude Code, Cursor, Codex, and any MCP client. 
Finds relevant code by meaning, remembers decisions across sessions, and cuts token costs by 90%+.

[![Demo GIF](docs/demo.gif)](docs/demo.gif)
<!-- TODO: Record 15-second GIF showing: "Where is auth middleware?" → instant relevant files → token savings report -->

### Why stars?
- 🧠 **Cross-session memory** — Switch from Claude to GPT-4 without losing context (handoffs)
- ⚡ **Token-slim router** — Exposes only the tools needed for the task, not 40+ tools
- 🔒 **Local-first** — Runs on CPU, no cloud required, privacy-preserving
- 🤝 **Multi-agent delegation** — Splits large tasks across parallel workers safely
- 📊 **90%+ token savings** — Sends only relevant snippets, not entire files

[Quick Start](#quick-start) • [Features](#features) • [How it works](#how-it-works) • [Configuration](#configuration)

</div>

---

## The Problem

Your AI coding agent forgets everything between sessions. It re-reads files it already saw, wastes tokens on irrelevant context, and can't switch models mid-task without losing state.

## The Solution

Context Broker sits between your editor and your codebase as a **context layer**. It indexes your code semantically, caches embeddings locally, and maintains persistent memory across sessions.

**One-line pitch:** *It's like having a senior dev who remembers every decision and can instantly find any pattern in the code.*

## Quick Start

### Prerequisites
- Python 3.13+
- UV package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/InSelfControll/context-broker-mcp.git
cd context-broker

# Install dependencies
uv sync
```

### MCP Client Configuration

Add to your MCP client (Claude Desktop, Cursor, etc.):

**Using UV (Recommended):**
```json
{
  "mcpServers": {
    "context-broker": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp", "python", "/full/path/to/context-broker/context-broker.py"],
      "env": {
        "CONTEXT_BROKER_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

**Using Python directly:**
```json
{
  "mcpServers": {
    "context-broker": {
      "command": "python",
      "args": ["/full/path/to/context-broker/context-broker.py"],
      "env": {
        "CONTEXT_BROKER_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

### One-Command Setup (Recommended)

Configure your specific editor automatically:

```bash
# For Claude Code
context-broker integration-config --host claude-code --project-root /absolute/path/to/project

# For Cursor
context-broker integration-config --host cursor --project-root /absolute/path/to/project

# For Codex
context-broker integration-config --host codex --project-root /absolute/path/to/project
```

This automatically merges the MCP config and installs the Context Broker skill.

## Features

- 🔍 **Semantic Code Search** — Find code by describing what you need in plain English
- 🧠 **Cross-Session Memory** — Save and load context between different AI models (Claude ↔ GPT-4 ↔ local models)
- 🤝 **Multi-Agent Delegation** — Split large tasks across 2-4 parallel workers with safety gates
- ⚡ **Token-Slim Router** — Only expose relevant tools for each task, reducing context bloat
- 💾 **Smart Caching** — Persistent embeddings with file modification tracking
- 📊 **Token Efficiency Reports** — See exactly how many tokens you're saving (typically 80-95%)
- 🚫 **Respects Ignore Files** — Reads `.gitignore` and `.dockerignore` automatically
- 🔒 **Local-first Privacy** — Runs on CPU, no cloud required, works offline
- 🌐 **Web Dashboard** — Browse stored contexts and sessions visually
- 🔄 **Model Handoffs** — Transfer complete session state (decisions, constraints, failures) between models

## How It Works

```
You: "How does authentication work?"
        ↓
Context Broker: [Semantic Search] → Finds auth middleware, user model, login endpoints
        ↓
Returns: Relevant snippets only (not full files) + Token savings report
```

### Key Capabilities

**1. Semantic Search**
Uses sentence transformers to understand code meaning. Search "database connection" finds `db.py`, `connection_pool.rs`, or `DatabaseConfig.java` regardless of naming conventions.

**2. Model Handoffs (Unique Feature)**
Switch AI models mid-task without losing context:

```python
# Save current state
handoff_id = save_model_handoff(
    goal="Fix authentication bug",
    decisions=["Using JWT not sessions", "Keep existing public API"],
    constraints=["Must support OAuth2"],
    failed_tasks=[{"task": "Database migration", "failure_reason": "Schema mismatch"}]
)

# Load in different model later
load_model_handoff(handoff_id)  # Restores complete context
```

**3. Multi-Agent Delegation**
For large tasks, Context Broker can spawn parallel workers:

```python
delegate_large_task(
    task="Refactor authentication system",
    context_snapshot=current_context,
    model="gpt-4"  # Uses your specified model
)
# Returns: 2-4 independent proposals + integration review
```

## Architecture

Context Broker uses a **Tool-Task-Codebase (TTC)** modular architecture:

- **Indexer**: Embeds code semantically using local ML models
- **Context Manager**: Handles cross-session persistence (Honcho/Redis/local JSON)
- **Router**: Ranks and exposes only relevant tools per task
- **Shared Service**: One broker instance serves multiple AI agents simultaneously

For detailed architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTEXT_BROKER_PROJECT_ROOT` | Default project root | Auto-detected |
| `CONTEXT_BROKER_EMBEDDING_MODEL` | Sentence-transformers model | `all-MiniLM-L6-v2` |
| `CONTEXT_BROKER_DEVICE` | Torch device (`cpu`, `cuda`, `mps`) | `cpu` |
| `CONTEXT_BROKER_CONTEXT_BACKEND` | Cross-chat backend: `none`, `honcho`, `redis` | `none` |
| `CONTEXT_BROKER_STORAGE_MODE` | Storage: `global`, `in-project`, `both` | `both` |

[See full configuration reference →](#detailed-configuration)

## Use Cases

**Switching Models Mid-Task:**
> You're debugging with Claude Code but hit the context limit. Save a handoff, switch to GPT-4 or a local model, and continue exactly where you left off—with all decisions and failed approaches intact.

**Large Refactors:**
> Delegate "Migrate from REST to GraphQL" to 4 parallel workers: one analyzes schema, one handles resolvers, one updates types, one reviews integration. Context Broker merges the proposals safely.

**New Team Member Onboarding:**
> Ask "How does error handling work here?" and get the 5 most relevant files instantly, not a 10,000-line codebase dump.

## Performance

- **First Search**: 1-5 seconds (depending on codebase size)
- **Subsequent Searches**: <100ms (cached embeddings)
- **Memory Usage**: ~100MB base + ~1MB per 100 files
- **Token Efficiency**: Typically saves 80-95% of tokens vs. sending entire codebase

## Documentation

- [Usage Guide](Usage.md) — Detailed workflows and examples
- [Architecture](ARCHITECTURE.md) — Technical deep dive
- [Contributing](CONTRIBUTING.md) — Development setup

## Supported File Types

**Languages:** Python, JavaScript, TypeScript, Go, Rust, Java, HTML, CSS, Shell, SQL  
**Config:** JSON, TOML, YAML, XML, Properties, Gradle  
**Docs:** Markdown

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

<div align="center">

**If this saved you tokens or time, consider starring ⭐ the repo!**

</div>
