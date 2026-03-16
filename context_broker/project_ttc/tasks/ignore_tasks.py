"""
Ignore-pattern loading and evaluation tasks.
"""

import fnmatch
import os
from pathlib import Path

from context_broker.utils import log
from context_broker.project_ttc.tools.ignore_tools import match_double_star, parse_ignore_file


def should_ignore(path: str, rel_path: str, patterns: list[str], ignore_dirs: set[str]) -> bool:
    """Determine whether a path should be ignored."""
    for part in Path(path).parts:
        if part in ignore_dirs:
            return True

    ignored = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if negated:
            pattern = pattern[1:]
        if not pattern:
            continue

        anchored = pattern.startswith("/")
        clean_pattern = pattern.lstrip("/").rstrip("/")
        is_dir_pattern = pattern.endswith("/")

        if "**" in clean_pattern:
            matched = match_double_star(rel_path, clean_pattern)
        elif anchored:
            matched = fnmatch.fnmatch(rel_path, clean_pattern)
        else:
            basename = os.path.basename(rel_path)
            matched = fnmatch.fnmatch(rel_path, clean_pattern) or fnmatch.fnmatch(basename, clean_pattern)

        if matched and is_dir_pattern:
            if not (rel_path.startswith(clean_pattern + os.sep) or rel_path == clean_pattern):
                matched = False
        if matched:
            ignored = not negated
    return ignored


def load_ignore_patterns(project_root: str | Path) -> list[str]:
    """Load patterns from .gitignore and .dockerignore."""
    patterns: list[str] = []
    project_root = Path(project_root)

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        gitignore_patterns = parse_ignore_file(gitignore_path)
        patterns.extend(gitignore_patterns)
        log(f"📄 Loaded {len(gitignore_patterns)} patterns from .gitignore")

    dockerignore_path = project_root / ".dockerignore"
    if dockerignore_path.exists():
        dockerignore_patterns = parse_ignore_file(dockerignore_path)
        patterns.extend(dockerignore_patterns)
        log(f"📄 Loaded {len(dockerignore_patterns)} patterns from .dockerignore")

    return patterns
