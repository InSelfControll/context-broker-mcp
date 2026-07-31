"""Tests for local literal/regex search and router literal_search intent."""

from __future__ import annotations

from pathlib import Path

from context_broker.indexer import literal_search
from context_broker.router_ttc.codebase.api import (
    execute_selected_tool,
    route_task,
)
from context_broker.router_ttc.tools.default_tools import default_tool_descriptors
from context_broker.router_ttc.tools.registry_tools import ToolRegistry


def _make_project(tmp_path: Path) -> str:
    """Create a small fake project with known content to search."""
    (tmp_path / "auth.py").write_text(
        "def authenticate(user, session_id):\n"
        "    token = create_token(session_id)\n"
        "    return token\n",
        encoding="utf-8",
    )
    (tmp_path / "models.py").write_text(
        "class Session:\n"
        "    def __init__(self, session_id):\n"
        "        self.session_id = session_id\n",
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "import os\n"
        "def helper():\n"
        "    pass\n",
        encoding="utf-8",
    )
    return str(tmp_path)


def _patch_ignore_dirs(monkeypatch) -> None:
    """Remove 'tmp'/'temp' from DEFAULT_IGNORE_DIRS so tmp_path projects work.

    pytest's tmp_path lives under /tmp/... and 'tmp' is in the default
    ignore-dir set, so file collection would skip everything without this.
    """
    from context_broker.config import DEFAULT_IGNORE_DIRS
    from context_broker.indexer_ttc.tasks import literal_search_tasks

    cleaned = DEFAULT_IGNORE_DIRS - {"tmp", "temp"}
    monkeypatch.setattr(literal_search_tasks, "DEFAULT_IGNORE_DIRS", cleaned)


def test_literal_search_finds_exact_string(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search("session_id", root)

    assert result["total_matches"] >= 3
    paths = [r["relative_path"] for r in result["results"]]
    assert "auth.py" in paths
    assert "models.py" in paths
    # utils.py has no session_id
    assert "utils.py" not in paths

    auth_entry = next(r for r in result["results"] if r["relative_path"] == "auth.py")
    assert auth_entry["match_count"] == 2
    lines = [m["line"] for m in auth_entry["matches"]]
    assert 1 in lines  # def authenticate(user, session_id):
    assert 2 in lines  # token = create_token(session_id)


def test_literal_search_case_insensitive_default(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search("SESSION_ID", root)
    assert result["total_matches"] >= 3


def test_literal_search_case_sensitive(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search("SESSION_ID", root, case_sensitive=True)
    assert result["total_matches"] == 0


def test_literal_search_regex_mode(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search(r"def\s+\w+", root, use_regex=True)
    # def authenticate, def helper, def __init__
    assert result["total_matches"] >= 3


def test_literal_search_file_glob_filter(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search("session_id", root, file_glob="*.py")
    paths = {r["relative_path"] for r in result["results"]}
    assert "auth.py" in paths


def test_literal_search_no_matches(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    result = literal_search("nonexistent_pattern_xyz", root)
    assert result["total_matches"] == 0
    assert result["files_with_matches"] == 0
    assert result["results"] == []


def test_literal_search_empty_pattern_raises(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    try:
        literal_search("", root)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_detect_intent_literal_search_signals() -> None:
    from context_broker.router_ttc.tasks.router_tasks import detect_intent

    for query in [
        "find session_id in auth function",
        "where is the auth function defined",
        "grep for create_token",
        "which file has def authenticate",
    ]:
        intents = detect_intent(query)["intents"]
        assert "literal_search" in intents, f"Failed for: {query}"


def test_route_task_prefers_find_in_codebase_for_literal_queries(tmp_path: Path) -> None:
    registry = ToolRegistry(cache_dir=tmp_path / "registry")
    registry.register_many(default_tool_descriptors())

    result = route_task(
        "find session_id in the auth function",
        registry=registry,
        mode="recommend_tools",
    )
    selected_ids = [tool["id"] for tool in result["selected_tools"]]
    assert "find_in_codebase" in selected_ids
    # find_in_codebase should be first for literal queries
    assert selected_ids[0] == "find_in_codebase"
    assert "literal_search" in result["intent"]["intents"]


def test_route_task_semantic_query_does_not_force_literal(tmp_path: Path) -> None:
    registry = ToolRegistry(cache_dir=tmp_path / "registry2")
    registry.register_many(default_tool_descriptors())

    result = route_task(
        "how does the authentication system work",
        registry=registry,
        mode="recommend_tools",
    )
    selected_ids = [tool["id"] for tool in result["selected_tools"]]
    assert "literal_search" not in result["intent"]["intents"]
    # find_in_codebase should not be forced first for semantic queries
    if selected_ids:
        assert selected_ids[0] != "find_in_codebase" or "search_codebase_tool" in selected_ids


def test_execute_selected_tool_runs_find_in_codebase_locally(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    root = _make_project(tmp_path)
    registry = ToolRegistry(cache_dir=tmp_path / "exec_registry")
    registry.register_many(default_tool_descriptors())

    result = execute_selected_tool(
        "find_in_codebase",
        {"pattern": "session_id", "project_root": root},
        registry=registry,
        mode="execute_safe",
    )
    assert result["status"] == "ok"
    assert result["tool_id"] == "find_in_codebase"
    # The result should contain actual matches from the local search
    search_result = result["result"]
    assert search_result["total_matches"] >= 3