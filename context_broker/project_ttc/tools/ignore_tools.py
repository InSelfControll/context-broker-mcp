"""
Ignore-file parsing and wildcard matching helpers.
"""

import fnmatch
import os
from pathlib import Path

from context_broker.utils import log


def parse_ignore_file(filepath: Path) -> list[str]:
    """Parse ignore file and return gitignore-style patterns."""
    patterns: list[str] = []
    if not filepath.exists():
        return patterns
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
    except Exception as e:
        log(f"⚠️ Error reading ignore file {filepath}: {e}", "WARN")
    return patterns


def match_double_star(path: str, pattern: str) -> bool:
    """Match path against a pattern containing ** wildcards."""
    parts = pattern.split("/**/")
    if len(parts) == 1:
        if pattern.startswith("**/"):
            suffix = pattern[3:]
            return fnmatch.fnmatch(os.path.basename(path), suffix) or any(
                fnmatch.fnmatch("/".join(path.split("/")[i:]), suffix) for i in range(len(path.split("/")))
            )
        prefix = pattern.rstrip("/**")
        return path.startswith(prefix)

    prefix, suffix = parts[0], parts[1]
    if not path.startswith(prefix):
        return False
    remaining = path[len(prefix) :].lstrip("/")
    path_parts = remaining.split("/")
    for i in range(len(path_parts)):
        candidate = "/".join(path_parts[i:])
        if fnmatch.fnmatch(candidate, suffix) or fnmatch.fnmatch(candidate, suffix.lstrip("/")):
            return True
    return False
