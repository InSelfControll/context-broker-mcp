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


def read_file_content(
    filepath: str, max_chars: int = 3000, *, strict_encoding: bool = False
) -> Optional[str]:
    """Read file content safely with encoding handling.

    SECURITY NOTE: This function performs content-based secret detection.
    If a file contains secret-key signatures (e.g., API_KEY=..., PASSWORD=...),
    it is blocked and None is returned. The block is logged for audit purposes.
    """
    try:
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative")
        blocked, reason = is_secret_file(filepath, filepath)
        if blocked:
            audit_log_secret_block(filepath, reason, operation="read")
            return None
        with open(
            filepath, "r", encoding="utf-8", errors="strict" if strict_encoding else "ignore"
        ) as f:
            content = f.read(max_chars)
    except Exception:
        return None

    # SECURITY: Content-based secret detection (catches renamed .env files)
    is_secret, reason = is_secret_file(filepath, filepath, content=content)
    if is_secret:
        audit_log_secret_block(filepath, reason, operation="read")
        log(f"🔒 SECURITY: Blocked read of '{filepath}' — {reason}", level="WARN")
        return None

    return content
