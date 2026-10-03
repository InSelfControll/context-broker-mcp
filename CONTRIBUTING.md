<div align="center">

# 🤝 Contributing to Context Broker

**Thanks for helping make AI coding assistants cheaper and smarter!**

[![⭐ Star on GitHub](https://img.shields.io/github/stars/InSelfControll/context-broker-mcp?style=social)](https://github.com/InSelfControll/context-broker-mcp)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[🏠 README](README.md) · [📖 Usage](Usage.md) · [🏗️ Architecture](ARCHITECTURE.md)

</div>

---

Thank you for your interest in contributing to Context Broker! This document provides guidelines and information for developers.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Testing](#testing)
- [Adding New Features](#adding-new-features)
- [Submitting Changes](#submitting-changes)

---

## Development Setup

### Prerequisites

- Python 3.13+
- UV package manager (recommended)

### Setup Steps

```bash
# Clone the repository
git clone <repo-url>
cd context-broker

# Install dependencies
uv sync

# Install in development mode
pip install -e .

# Run the server
python context-broker.py
```

---

## Project Structure

```
context-broker/
├── context_broker/           # Main package
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Configuration constants
│   ├── utils.py             # Utility functions
│   ├── project.py           # Project detection & ignores
│   ├── storage.py           # JSON persistence
│   ├── indexer.py           # Search & embeddings
│   └── server.py            # MCP server implementation
├── context-broker.py        # Main entry point
├── main.py                  # Alternative entry point
├── pyproject.toml           # Project configuration
├── README.md                # User documentation
├── Usage.md                 # Detailed usage guide
├── ARCHITECTURE.md          # Architecture documentation
└── CONTRIBUTING.md          # This file
```

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `config.py` | Centralized configuration, environment variables |
| `utils.py` | Logging, token counting, path utilities |
| `project.py` | Project root detection, ignore pattern parsing |
| `storage.py` | JSON persistence with multi-mode storage |
| `indexer.py` | File indexing, embedding generation, search |
| `server.py` | MCP tools, resources, and prompts |

---

## Code Style

### Python Style Guide

We follow PEP 8 with some modifications:

```python
# Use type hints for all function signatures
def search_codebase(query: str, project_root: str, top_k: int = 5) -> dict[str, Any]:
    """
    Brief description of the function.
    
    Longer description explaining behavior, edge cases, etc.
    
    Args:
        query: Description of parameter
        project_root: Description of parameter
        top_k: Description with default
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When this error occurs
    """
    pass
```

### Naming Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`

### Import Order

```python
# 1. Standard library
import os
import sys
from pathlib import Path
from typing import Any, Optional

# 2. Third-party
import numpy as np
from fastmcp import FastMCP

# 3. Local modules
from context_broker.config import STORAGE_MODE
from context_broker.utils import log
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=context_broker

# Run specific test file
pytest tests/test_indexer.py
```

### Writing Tests

```python
# tests/test_project.py
import pytest
from context_broker.project import find_project_root, should_ignore


def test_find_project_root_detects_git():
    """Test that .git directory is detected as project root."""
    # Arrange
    test_dir = "/tmp/test-project"
    os.makedirs(os.path.join(test_dir, ".git"))
    
    # Act
    result = find_project_root(test_dir)
    
    # Assert
    assert result == test_dir
    
    # Cleanup
    shutil.rmtree(test_dir)


def test_should_ignore_respects_patterns():
    """Test that gitignore patterns are respected."""
    assert should_ignore(
        "/project/node_modules/test.js",
        "node_modules/test.js",
        ["node_modules/"],
        set()
    ) == True
```

---

## Adding New Features

### Adding a New MCP Tool

1. Define the tool in `context_broker/server.py`:

```python
@mcp.tool()
def my_new_tool(param: str, project_root: str = "") -> str:
    """
    Description of what the tool does.
    
    Args:
        param: Description of parameter
        project_root: Project root path (auto-detected if not provided)
        
    Returns:
        Description of return value
    """
    root = resolve_project_root(project_root)
    
    try:
        # Implementation
        result = do_something(param, root)
        return f"Success: {result}"
    except Exception as e:
        log(f"❌ Error: {e}", "ERROR")
        return f"Error: {str(e)}"
```

2. Add tests in `tests/test_server.py`
3. Update `README.md` and `Usage.md` with documentation

### Adding a New Storage Mode

1. Update `context_broker/config.py`:

```python
class StorageMode:
    GLOBAL = "global"
    IN_PROJECT = "in-project"
    BOTH = "both"
    CLOUD = "cloud"  # New mode
```

2. Implement in `context_broker/storage.py`:

```python
def get_storage_dir(...) -> Path:
    # Add handling for new mode
    if mode == StorageMode.CLOUD:
        return _get_cloud_path(project_name)
```

### Adding Support for New File Types

Update `context_broker/config.py`:

```python
SUPPORTED_EXTENSIONS: list[str] = [
    # Existing extensions...
    "*.rb",      # Ruby
    "*.php",     # PHP
    "*.ex",      # Elixir
    "*.exs",
]
```

---

## Architecture Decisions

When making changes, consider these architectural principles:

### 1. Single Responsibility
Each module should have one reason to change.

```python
# Good: indexer.py only handles search
# Bad: indexer.py also handling HTTP requests
```

### 2. Dependency Direction
Dependencies should point inward:

```
server.py → indexer.py → utils.py → config.py
```

### 3. Configuration Over Code
Prefer environment variables and config over hardcoding:

```python
# Good
TIMEOUT = os.environ.get("CONTEXT_BROKER_TIMEOUT", 30)

# Bad
TIMEOUT = 30  # Can't be changed without code change
```

### 4. Fail Gracefully
Always handle errors and provide meaningful messages:

```python
try:
    result = risky_operation()
except FileNotFoundError:
    log("⚠️ File not found, using default", "WARN")
    result = get_default()
except Exception as e:
    log(f"❌ Unexpected error: {e}", "ERROR")
    raise
```

---

## Submitting Changes

### Before Submitting

1. **Run tests**: Ensure all tests pass
2. **Check type hints**: Run `mypy context_broker/`
3. **Format code**: Run `black context_broker/`
4. **Update docs**: Update README.md if behavior changes

### Commit Message Format

Follow conventional commits:

```
feat: add new search filter for file types
fix: handle edge case in ignore pattern parsing
docs: update architecture diagram
refactor: simplify storage module
test: add tests for project detection
```

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

---

## Questions?

If you have questions about contributing:

1. Check existing documentation (README.md, Usage.md, ARCHITECTURE.md)
2. Search existing issues
3. Open a new issue with the "question" label

Thank you for contributing to Context Broker! 🚀
