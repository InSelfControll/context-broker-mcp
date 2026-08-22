"""
Project root detection and resolution tasks.
"""

import os
from pathlib import Path
from typing import Optional

from context_broker.config import DEFAULT_PROJECT_ROOT, PROJECT_MARKERS, WORKTREE_SHARED_ROOT
from context_broker.project_ttc.tools.worktree_tools import resolve_worktree_main_root
from context_broker.utils import log


def _share_worktree_root(root: str) -> str:
    """Map a linked worktree root to the main checkout when sharing is on."""
    if not WORKTREE_SHARED_ROOT:
        return root
    main_root = resolve_worktree_main_root(root)
    if main_root and main_root != root:
        log(f"🔗 Git worktree detected; sharing project root with main checkout: {main_root}")
        return main_root
    return root


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
    if project_root:
        resolved = Path(project_root).resolve()
        log(f"📁 Using explicit project root: {resolved}")
        return _share_worktree_root(str(resolved))
    if DEFAULT_PROJECT_ROOT:
        resolved = Path(DEFAULT_PROJECT_ROOT).resolve()
        log(f"📁 Using env project root: {resolved}")
        return _share_worktree_root(str(resolved))

    detected = find_project_root()
    if detected:
        log(f"🔍 Auto-detected project root: {detected}")
        return _share_worktree_root(detected)

    cwd = os.getcwd()
    log(f"⚠ No project markers found, using CWD: {cwd}", "WARN")
    return cwd


def get_project_name(project_root: str | Path) -> str:
    """Extract clean project name from root path."""
    return Path(project_root).name or "unknown"
