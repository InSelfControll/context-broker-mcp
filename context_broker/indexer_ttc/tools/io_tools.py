"""
Low-level file I/O helpers.
"""

from typing import Optional


def read_file_content(filepath: str, max_chars: int = 3000) -> Optional[str]:
    """Read file content safely with encoding handling."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except Exception:
        return None
