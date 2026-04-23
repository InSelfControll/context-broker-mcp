"""Compatibility wrapper for agents management API."""

from context_broker.agents_ttc.codebase.api import (
    ensure_agents_md,
    generate_agents_md,
    scan_for_missing_agents_md,
    validate_agents_md,
)

__all__ = [
    "ensure_agents_md",
    "validate_agents_md",
    "generate_agents_md",
    "scan_for_missing_agents_md",
]
