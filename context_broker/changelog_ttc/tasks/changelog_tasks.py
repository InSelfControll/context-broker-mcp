"""High-level changelog management tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_broker.changelog_ttc.tools.changelog_tools import (
    get_changelog_summary,
    update_changelog,
    validate_changelog,
)
from context_broker.utils import log


def ensure_changelog(project_root: str) -> dict[str, Any]:
    """Ensure CHANGELOG.md exists and is up to date.

    Creates a new CHANGELOG.md if missing, or updates it with recent commits.

    Returns:
        Dict with status and message.
    """
    root = Path(project_root).resolve()
    changelog_path = root / "CHANGELOG.md"

    log(f"📝 Checking CHANGELOG.md for {root.name}...")
    result = update_changelog(changelog_path, version="Unreleased", cwd=str(root))
    return result


def check_changelog_status(project_root: str) -> dict[str, Any]:
    """Check if CHANGELOG.md is up to date with git history.

    Returns:
        Dict with validation results.
    """
    root = Path(project_root).resolve()
    changelog_path = root / "CHANGELOG.md"

    log(f"📋 Validating CHANGELOG.md for {root.name}...")
    return validate_changelog(changelog_path)


def generate_changelog_for_version(
    project_root: str,
    version: str,
    since: str = "",
) -> dict[str, Any]:
    """Generate a changelog section for a specific version.

    Args:
        project_root: Project root path.
        version: Version label (e.g., "0.2.0").
        since: Git ref to start from (auto-detected if empty).

    Returns:
        Dict with status and generated content.
    """
    root = Path(project_root).resolve()
    changelog_path = root / "CHANGELOG.md"

    log(f"🚀 Generating changelog for version {version}...")
    result = update_changelog(
        changelog_path,
        version=version,
        since=since,
        cwd=str(root),
    )
    return result


def get_changelog_stats(project_root: str) -> dict[str, str]:
    """Get statistics about the current changelog.

    Returns:
        Dict with summary info.
    """
    root = Path(project_root).resolve()
    changelog_path = root / "CHANGELOG.md"
    return get_changelog_summary(changelog_path)
