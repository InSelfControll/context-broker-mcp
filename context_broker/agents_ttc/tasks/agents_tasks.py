"""High-level AGENTS.md management tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_broker.agents_ttc.tools.agents_tools import (
    extract_project_metadata,
    generate_agents_md_content,
    has_agents_md,
    read_agents_md,
    validate_agents_md_content,
    write_agents_md,
)
from context_broker.utils import log


def ensure_agents_md(project_root: str) -> dict[str, Any]:
    """Ensure AGENTS.md exists for a project. Create it if missing.

    Returns:
        Dict with status, path, and message.
    """
    root = Path(project_root).resolve()
    if has_agents_md(root):
        path = root / "AGENTS.md"
        log(f"✅ AGENTS.md already exists at {path}")
        return {
            "status": "exists",
            "path": str(path),
            "created": False,
            "message": f"AGENTS.md already exists at {path}",
        }

    log(f"📝 Generating AGENTS.md for {root.name}...")
    metadata = extract_project_metadata(root)
    content = generate_agents_md_content(metadata)
    path = write_agents_md(root, content)
    log(f"✅ Created AGENTS.md at {path}")

    return {
        "status": "created",
        "path": str(path),
        "created": True,
        "message": f"Created AGENTS.md at {path}",
    }


def validate_agents_md(project_root: str) -> dict[str, Any]:
    """Validate AGENTS.md for a project and report issues.

    Returns:
        Dict with validation results.
    """
    root = Path(project_root).resolve()
    content = read_agents_md(root)
    result = validate_agents_md_content(content)

    if not result["exists"]:
        log(f"⚠️ No AGENTS.md found for {root.name}")
        return {
            "status": "missing",
            "path": str(root / "AGENTS.md"),
            "valid": False,
            **result,
        }

    valid = result["has_goals"] and result["score"] >= 40
    status = "valid" if valid else "needs_improvement"
    log(f"📋 AGENTS.md validation for {root.name}: {status} (score {result['score']}/100)")

    return {
        "status": status,
        "path": str(root / "AGENTS.md"),
        "valid": valid,
        **result,
    }


def generate_agents_md(project_root: str, force: bool = False) -> dict[str, Any]:
    """Generate AGENTS.md for a project, optionally overwriting existing.

    Returns:
        Dict with status, path, and message.
    """
    root = Path(project_root).resolve()
    existing = has_agents_md(root)

    if existing and not force:
        path = root / "AGENTS.md"
        log(f"⚠️ AGENTS.md already exists at {path}. Use force=True to overwrite.")
        return {
            "status": "exists",
            "path": str(path),
            "created": False,
            "message": f"AGENTS.md already exists at {path}. Use force=True to overwrite.",
        }

    log(f"📝 Generating AGENTS.md for {root.name}...")
    metadata = extract_project_metadata(root)
    content = generate_agents_md_content(metadata)
    path = write_agents_md(root, content)

    status = "overwritten" if existing else "created"
    log(f"✅ {status.capitalize()} AGENTS.md at {path}")

    return {
        "status": status,
        "path": str(path),
        "created": True,
        "message": f"{status.capitalize()} AGENTS.md at {path}",
    }


def scan_for_missing_agents_md(project_root: str, max_depth: int = 3) -> list[dict[str, Any]]:
    """Scan a directory for subprojects missing AGENTS.md.

    Args:
        project_root: Root directory to scan.
        max_depth: Maximum depth to search for subprojects.

    Returns:
        List of dicts with project path and status.
    """
    root = Path(project_root).resolve()
    results: list[dict[str, Any]] = []

    from context_broker.config import PROJECT_MARKERS

    markers = [m[0] for m in PROJECT_MARKERS]

    def _scan(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        has_marker = any((path / marker).exists() for marker in markers)
        if has_marker:
            has_agents = has_agents_md(path)
            results.append({
                "path": str(path),
                "name": path.name,
                "has_agents_md": has_agents,
                "status": "ok" if has_agents else "missing",
            })
            # Don't recurse into identified projects
            return
        for child in path.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                _scan(child, depth + 1)

    try:
        _scan(root, 0)
    except PermissionError as e:
        log(f"⚠️ Permission error scanning {root}: {e}", "WARN")

    return results
