"""
Security tools for preventing secret leakage to external AI providers.

This module provides defense-in-depth protection against accidentally indexing,
embedding, or returning files that contain secrets, credentials, tokens,
passwords, API keys, or other sensitive data.

Design principle: filename patterns are used ONLY for files that ALMOST ALWAYS
contain secrets (e.g., .env, id_rsa). Files that SOMETIMES contain secrets but
are often just config (e.g., .npmrc, .yarnrc) are handled via content-based
SECRET_ENV_KEY_PATTERNS scanning instead. This reduces false positives while
maintaining security — if a .npmrc DOES contain an auth token, it is still
blocked by content scanning.

All blocking is LOGGED so users can audit what was blocked and why.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from context_broker.config import SECRET_ENV_KEY_PATTERNS, SECRET_FILE_PATTERNS
from context_broker.utils import log


def _match_secret_pattern(rel_path: str) -> tuple[bool, str]:
    """Check if a file path matches any secret file pattern.

    Returns:
        (is_secret, matched_pattern) tuple.
    """
    basename = os.path.basename(rel_path)
    for pattern in SECRET_FILE_PATTERNS:
        if fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(rel_path, pattern):
            return True, pattern
    return False, ""


def _scan_content_for_secrets(content: str) -> tuple[bool, str]:
    """Scan file content for secret-key signatures.

    This catches renamed .env files and other secret-bearing files that
    don't match filename patterns.

    Returns:
        (is_secret, matched_signature) tuple.
    """
    lines = content.splitlines()
    # Only scan first 100 lines — secrets are usually at the top of env files
    for line in lines[:100]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Sort signatures by length descending so longer/more specific
        # patterns match first (e.g., "SECRET_KEY" before "SECRET")
        for signature in sorted(SECRET_ENV_KEY_PATTERNS, key=len, reverse=True):
            if signature in stripped:
                return True, signature
    return False, ""


def is_secret_file(file_path: str, rel_path: str, content: str | None = None) -> tuple[bool, str]:
    """Determine whether a file should be blocked as a secret file.

    Checks in order:
      1. Filename/path pattern matching (fast, no I/O)
      2. Content signature scanning (if content is provided)

    Args:
        file_path: Absolute file path.
        rel_path: Path relative to project root.
        content: Optional file content for signature scanning.

    Returns:
        (is_secret, reason) tuple. If is_secret is True, reason explains why.
    """
    # 1. Filename pattern check
    matched, pattern = _match_secret_pattern(rel_path)
    if matched:
        return True, f"blocked by secret pattern '{pattern}'"

    # 2. Content signature check (only if content is provided)
    if content is not None:
        matched, signature = _scan_content_for_secrets(content)
        if matched:
            return True, f"blocked by content signature '{signature}'"

    return False, ""


def audit_log_secret_block(rel_path: str, reason: str, operation: str = "index") -> None:
    """Emit a security audit log when a secret file is blocked.

    This is separate from normal logging to make security events stand out.

    Args:
        rel_path: Relative path of the blocked file.
        reason: Why the file was blocked.
        operation: Which operation blocked it ('index', 'search', 'read').
    """
    log(
        f"🔒 SECURITY [{operation}]: Blocked '{rel_path}' — {reason}",
        level="WARN",
    )


def get_security_summary() -> dict[str, int]:
    """Return a summary of the current security configuration.

    Returns:
        Dict with pattern counts and content signatures.
    """
    return {
        "secret_file_patterns": len(SECRET_FILE_PATTERNS),
        "secret_content_signatures": len(SECRET_ENV_KEY_PATTERNS),
    }
