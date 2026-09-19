"""Stable storage identifiers shared by context backends, cache, and ledger."""

import hashlib
import os


def project_digest(project_root: str) -> str:
    """Return the existing project-scoped storage digest."""
    root = os.path.abspath(project_root or os.getcwd())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def normalize_identifier(value: str, default: str = "default") -> str:
    """Normalize identifiers while preserving existing persisted key formats.

    Characters outside ``[alnum - _ .]`` are replaced with ``-``. When that
    normalization is lossy, a short digest of the original identifier is
    appended so distinct caller-supplied ids can never collapse into the
    same Redis key or ledger file (session isolation).
    """
    candidate = (value or default).strip() or default
    normalized = "".join(c if c.isalnum() or c in {"-", "_", "."} else "-" for c in candidate)
    if normalized != candidate:
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:10]
        normalized = f"{normalized}-{digest}"
    return normalized
