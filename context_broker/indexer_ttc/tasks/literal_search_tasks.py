"""
Literal (regex/keyword) search tasks — local, no external LLM.

These tasks scan indexed files for exact or regex pattern matches and return
snippet windows around each hit. This lets the MCP answer precise queries
(e.g. "find session_id in the auth function") entirely locally without
delegating to an external LLM, reducing token usage.
"""

from __future__ import annotations

import os
import re
from typing import Any

from context_broker.config import DEFAULT_IGNORE_DIRS
from context_broker.indexer_ttc.tools.collect_tools import collect_project_files
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.utils import log

# Maximum matches per file to avoid overwhelming the response.
_MAX_MATCHES_PER_FILE = 20
# Characters of context shown on each side of a match.
_CONTEXT_CHARS = 80
# Maximum total matches returned across all files.
_MAX_TOTAL_MATCHES = 50


def _collect_files(project_root: str) -> list[str]:
    """Collect supported files under *project_root*, respecting ignores."""
    return collect_project_files(project_root, ignore_dirs=DEFAULT_IGNORE_DIRS)


def _build_regex(pattern: str, case_sensitive: bool, use_regex: bool) -> re.Pattern[str]:
    """Compile *pattern* into a regex, escaping it if regex mode is off."""
    flags = 0 if case_sensitive else re.IGNORECASE
    if not use_regex:
        pattern = re.escape(pattern)
    return re.compile(pattern, flags)


def _extract_match_snippet(
    content: str,
    match: re.Match[str],
    context_chars: int = _CONTEXT_CHARS,
) -> str:
    """Return a one-line snippet around *match* with ellipsis trimming."""
    start = max(0, match.start() - context_chars)
    end = min(len(content), match.end() + context_chars)
    snippet = content[start:end].replace("\n", "\\n")
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{snippet}{suffix}"


def literal_search(
    pattern: str,
    project_root: str,
    *,
    case_sensitive: bool = False,
    use_regex: bool = False,
    file_glob: str = "",
    max_matches: int = _MAX_TOTAL_MATCHES,
) -> dict[str, Any]:
    """Search indexed files for *pattern* and return precise matches.

    This runs **entirely locally** — no embedding model, no external LLM call.
    It scans file contents for literal or regex pattern matches and returns
    file paths, line numbers, and short context snippets so the caller can
    jump directly to the relevant code.

    Args:
        pattern: Literal string or regex pattern to search for.
        project_root: Root directory to search under.
        case_sensitive: Whether the search is case-sensitive.
        use_regex: Treat *pattern* as a regex instead of a literal string.
        file_glob: Optional extension filter (e.g. "*.py"). Empty = all supported.
        max_matches: Hard cap on total matches returned.

    Returns:
        Dict with query metadata, match list, and counts.
    """
    if not pattern:
        raise ValueError("pattern is required")
    if not project_root:
        raise ValueError("project_root is required")

    project_root = os.path.abspath(project_root)
    log(f"🔎 literal_search: pattern='{pattern[:60]}', root='{project_root}', regex={use_regex}")

    regex = _build_regex(pattern, case_sensitive=case_sensitive, use_regex=use_regex)
    files = _collect_files(project_root)

    # Optional extension filter
    if file_glob:
        files = [f for f in files if fnmatch_file(f, file_glob)]

    results: list[dict[str, Any]] = []
    total_matches = 0
    files_with_matches = 0
    files_searched = 0

    for file_path in sorted(files):
        if total_matches >= max_matches:
            break
        content = read_file_content(file_path, max_chars=512_000)
        if content is None:
            continue
        files_searched += 1

        file_matches: list[dict[str, Any]] = []
        file_match_count = 0
        for match in regex.finditer(content):
            if file_match_count >= _MAX_MATCHES_PER_FILE:
                break
            line_num = content.count("\n", 0, match.start()) + 1
            file_matches.append(
                {
                    "line": line_num,
                    "match": match.group(),
                    "snippet": _extract_match_snippet(content, match),
                }
            )
            file_match_count += 1
            total_matches += 1
            if total_matches >= max_matches:
                break

        if file_matches:
            files_with_matches += 1
            rel_path = os.path.relpath(file_path, project_root)
            results.append(
                {
                    "path": file_path,
                    "relative_path": rel_path,
                    "match_count": len(file_matches),
                    "matches": file_matches,
                }
            )

    from context_broker.project import get_project_name

    project_name = get_project_name(project_root)
    log(
        f"✅ literal_search complete: {total_matches} matches in "
        f"{files_with_matches}/{files_searched} files"
    )

    return {
        "query": pattern,
        "project": project_name,
        "project_root": project_root,
        "use_regex": use_regex,
        "case_sensitive": case_sensitive,
        "file_glob": file_glob,
        "results": results,
        "total_matches": total_matches,
        "files_with_matches": files_with_matches,
        "files_searched": files_searched,
        "truncated": total_matches >= max_matches,
    }


def fnmatch_file(file_path: str, glob_pattern: str) -> bool:
    """Check if *file_path* basename matches *glob_pattern*."""
    import fnmatch

    return fnmatch.fnmatch(os.path.basename(file_path), glob_pattern)