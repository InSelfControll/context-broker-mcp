"""
Project root detection and resolution tasks.
"""

import os
from pathlib import Path
from typing import Optional

from context_broker.config import DEFAULT_PROJECT_ROOT, PROJECT_MARKERS
from context_broker.utils import log


def find_project_root(start_path: str | Path = "") -> Optional[str]:
    """Auto-detect project root by marker score while traversing parents."""
    if not start_path:
        start_path = os.getcwd()

    current = Path(start_path).resolve()
    best_root: Optional[Path] = None
    best_score = 0

    while current != current.parent:
        score = 0
        for marker, points in PROJECT_MARKERS:
            if (current / marker).exists():
                score += points
        if score > best_score:
            best_score = score
            best_root = current
            if score >= 100:
                break
        current = current.parent
    return str(best_root) if best_root else None


def resolve_project_root(project_root: str = "") -> str:
    """Resolve project root from explicit arg, env, auto-detect, then CWD."""
    from context_broker.shared_ttc.tools.scope import PROJECT_ROOT

    bound_root = PROJECT_ROOT.get()
    if bound_root:
        if project_root and str(Path(project_root).resolve()) != bound_root:
            raise ValueError("project_root does not match this connection's project")
        return bound_root
    if project_root:
        resolved = Path(project_root).resolve()
        log(f"📁 Using explicit project root: {resolved}")
        return str(resolved)
    if DEFAULT_PROJECT_ROOT:
        resolved = Path(DEFAULT_PROJECT_ROOT).resolve()
        log(f"📁 Using env project root: {resolved}")
        return str(resolved)

    detected = find_project_root()
    if detected:
        log(f"🔍 Auto-detected project root: {detected}")
        return detected

    cwd = os.getcwd()
    log(f"⚠️ No project markers found, using CWD: {cwd}", "WARN")
    return cwd


def get_project_name(project_root: str | Path) -> str:
    """Extract clean project name from root path."""
    return Path(project_root).name or "unknown"
