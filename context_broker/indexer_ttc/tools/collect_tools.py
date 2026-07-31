"""Safe project file collection for indexing and literal search.

Uses a single ``os.walk`` pass that prunes ignored directories up front and
never follows directory symlinks by default. Recursive ``glob`` over large
trees (or trees that symlink into ``/nix/store``) is the main cause of MCP
``search_context`` timeouts past the client 300s budget.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from typing import Optional

from context_broker.config import (
    DEFAULT_IGNORE_DIRS,
    INDEX_FOLLOW_SYMLINKS,
    INDEX_MAX_FILE_BYTES,
    SUPPORTED_EXTENSIONS,
)
from context_broker.project import load_ignore_patterns, should_ignore
from context_broker.project_ttc.tasks.ignore_tasks import matches_ignored_file_pattern
from context_broker.utils import log


def _extension_filters(extensions: Iterable[str]) -> list[str]:
    """Normalize ``*.py`` / ``.py`` style filters for basename matching."""
    filters: list[str] = []
    for item in extensions:
        text = str(item).strip()
        if not text:
            continue
        if text.startswith("*"):
            filters.append(text)
        elif text.startswith("."):
            filters.append(f"*{text}")
        else:
            filters.append(text if "*" in text else f"*.{text.lstrip('.')}")
    return filters


def matches_supported_extension(filename: str, extensions: Iterable[str]) -> bool:
    """Return True when *filename* matches one of the supported globs."""
    basename = os.path.basename(filename)
    for pattern in _extension_filters(extensions):
        if fnmatch.fnmatch(basename, pattern):
            return True
    return False


def collect_project_files(
    project_root: str,
    *,
    extensions: Optional[Iterable[str]] = None,
    ignore_dirs: Optional[set[str]] = None,
    ignore_patterns: Optional[list[str]] = None,
    follow_symlinks: Optional[bool] = None,
    max_file_bytes: Optional[int] = None,
) -> list[str]:
    """Collect indexable files under *project_root* without symlink escapes.

    Args:
        project_root: Absolute or relative project root.
        extensions: Glob list like ``SUPPORTED_EXTENSIONS``. Defaults to config.
        ignore_dirs: Directory basenames always pruned. Defaults to config.
        ignore_patterns: Extra gitignore-style patterns. Loaded from the project
            when omitted.
        follow_symlinks: Whether to walk through directory symlinks. Defaults to
            ``INDEX_FOLLOW_SYMLINKS`` (False). File symlinks are also skipped
            unless this is True.
        max_file_bytes: Skip regular files larger than this. Defaults to
            ``INDEX_MAX_FILE_BYTES``. ``0`` disables the size cap.

    Returns:
        Sorted absolute file paths.
    """
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        return []

    ext_list = list(extensions) if extensions is not None else list(SUPPORTED_EXTENSIONS)
    dirs = set(ignore_dirs) if ignore_dirs is not None else set(DEFAULT_IGNORE_DIRS)
    patterns = (
        list(ignore_patterns)
        if ignore_patterns is not None
        else load_ignore_patterns(root)
    )
    follow = INDEX_FOLLOW_SYMLINKS if follow_symlinks is None else bool(follow_symlinks)
    size_cap = INDEX_MAX_FILE_BYTES if max_file_bytes is None else int(max_file_bytes)

    files: list[str] = []
    skipped_symlink_dirs = 0
    skipped_large = 0
    skipped_binary = 0
    pruned_dirs = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow, topdown=True):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        keep: list[str] = []
        for name in dirnames:
            child_abs = os.path.join(dirpath, name)
            child_rel = name if not rel_dir else os.path.join(rel_dir, name)

            if name in dirs:
                pruned_dirs += 1
                continue
            if not follow and os.path.islink(child_abs):
                skipped_symlink_dirs += 1
                continue
            if should_ignore(child_abs, child_rel, patterns, dirs):
                pruned_dirs += 1
                continue
            keep.append(name)
        dirnames[:] = keep

        for name in filenames:
            file_rel = name if not rel_dir else os.path.join(rel_dir, name)
            # Skip ISOs / archives / media before extension or stat work.
            if matches_ignored_file_pattern(file_rel):
                skipped_binary += 1
                continue
            if not matches_supported_extension(name, ext_list):
                continue
            file_abs = os.path.join(dirpath, name)

            if not follow and os.path.islink(file_abs):
                continue
            if should_ignore(file_abs, file_rel, patterns, dirs):
                continue
            if size_cap > 0:
                try:
                    if os.path.getsize(file_abs) > size_cap:
                        skipped_large += 1
                        continue
                except OSError:
                    continue
            files.append(file_abs)

    files.sort()
    if skipped_symlink_dirs or skipped_large or skipped_binary or pruned_dirs:
        log(
            "📁 collect_project_files: "
            f"{len(files)} files "
            f"(pruned_dirs={pruned_dirs}, "
            f"skipped_symlink_dirs={skipped_symlink_dirs}, "
            f"skipped_binary={skipped_binary}, "
            f"skipped_large={skipped_large}, follow_symlinks={follow})"
        )
    return files
