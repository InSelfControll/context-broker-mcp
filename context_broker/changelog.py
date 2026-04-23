"""Compatibility wrapper for changelog management API."""

from context_broker.changelog_ttc.codebase.api import (
    check_changelog_status,
    ensure_changelog,
    generate_changelog_for_version,
    get_changelog_stats,
)

__all__ = [
    "ensure_changelog",
    "check_changelog_status",
    "generate_changelog_for_version",
    "get_changelog_stats",
]
