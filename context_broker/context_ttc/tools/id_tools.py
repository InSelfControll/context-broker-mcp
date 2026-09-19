"""Collision-free identifier normalization for context storage keys."""

import hashlib


def safe_id(value: str, default: str = "default") -> str:
    """Normalize an external identifier for use in storage keys.

    Characters outside ``[alnum - _ .]`` are replaced with ``-``. When that
    normalization is lossy, a short digest of the original identifier is
    appended so distinct caller-supplied ids can never collapse into the
    same Redis key or ledger file (session isolation).
    """
    candidate = (value or default).strip() or default
    normalized = "".join(
        c if c.isalnum() or c in {"-", "_", "."} else "-" for c in candidate
    )
    if normalized != candidate:
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:10]
        normalized = f"{normalized}-{digest}"
    return normalized
