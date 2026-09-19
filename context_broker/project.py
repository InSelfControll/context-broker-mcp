"""
Compatibility wrapper for project path API.
"""

from context_broker.project_ttc.codebase.api import (
    find_project_root,
    get_project_name,
    load_ignore_patterns,
    parse_ignore_file,
    resolve_project_root,
    resolve_worktree_main_root,
    should_ignore,
)

__all__ = [
    "parse_ignore_file",
    "should_ignore",
    "load_ignore_patterns",
    "find_project_root",
    "resolve_project_root",
    "resolve_worktree_main_root",
    "get_project_name",
]
