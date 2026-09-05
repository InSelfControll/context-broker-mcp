"""Stable storage identifiers shared by context backends, cache, and ledger."""

import hashlib
import os


def project_digest(project_root: str) -> str:
    """Return the existing project-scoped storage digest."""
    root = os.path.abspath(project_root or os.getcwd())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def normalize_identifier(value: str, default: str = "default") -> str:
    """Normalize identifiers while preserving existing persisted key formats."""
    candidate = (value or default).strip() or default
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "-" for c in candidate)
