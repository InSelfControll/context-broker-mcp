"""
Low-level file I/O helpers.

SECURITY: All file reads are screened for secret content before being
returned. Files containing secret key signatures are blocked and logged.
"""

from typing import Optional

from context_broker.security_ttc.tools import (
    audit_log_secret_block,
    is_secret_file,
)
from context_broker.utils import log


def read_file_content(filepath: str, max_chars: int = 3000) -> Optional[str]:
    """Read file content safely with encoding handling.

    SECURITY NOTE: This function performs content-based secret detection.
    If a file contains secret-key signatures (e.g., API_KEY=..., PASSWORD=...),
    it is blocked and None is returned. The block is logged for audit purposes.
    """
    try:
        # Read a small preview first for content scanning (first 4KB)
        preview_chars = min(max_chars, 4096)
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            preview = f.read(preview_chars)
    except Exception:
        return None

    # SECURITY: Content-based secret detection (catches renamed .env files)
    is_secret, reason = is_secret_file(filepath, filepath, content=preview)
    if is_secret:
        audit_log_secret_block(filepath, reason, operation="read")
        log(f"🔒 SECURITY: Blocked read of '{filepath}' — {reason}", level="WARN")
        return None

    # If preview was smaller than max_chars, we already have full content
    if preview_chars >= max_chars:
        return preview

    # Read remaining content if needed
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            f.read(preview_chars)  # Skip already-read preview
            remainder = f.read(max_chars - preview_chars)
            return preview + remainder
    except Exception:
        # Return what we have even if full read fails
        return preview
