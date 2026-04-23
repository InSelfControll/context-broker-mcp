"""High-level documentation management tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_broker.docs_ttc.tools.docs_tools import (
    ensure_feature_docs,
    generate_feature_docs,
    get_docs_summary,
    scan_for_missing_docs,
)
from context_broker.utils import log


def ensure_docs(project_root: str, since: str = "", max_count: int = 50) -> dict[str, Any]:
    """Ensure documentation exists for all recent feature changes."""
    root = Path(project_root).resolve()
    log(f"📝 Ensuring feature docs for {root.name}...")
    return ensure_feature_docs(str(root), since=since, max_count=max_count)


def scan_docs(project_root: str, since: str = "", max_count: int = 50) -> dict[str, Any]:
    """Scan for missing feature documentation."""
    root = Path(project_root).resolve()
    log(f"🔍 Scanning for missing docs in {root.name}...")
    return scan_for_missing_docs(str(root), since=since, max_count=max_count)


def docs_stats(project_root: str) -> dict[str, Any]:
    """Get statistics about feature documentation."""
    root = Path(project_root).resolve()
    return get_docs_summary(str(root))
