"""Tests for git worktree main-root resolution and shared project roots."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from context_broker.project_ttc.tasks import root_tasks
from context_broker.project_ttc.tools.worktree_tools import resolve_worktree_main_root

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    main = tmp_path / "main"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.com"], main)
    _git(["config", "user.name", "test"], main)
    (main / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], main)
    _git(["commit", "-m", "init"], main)
    return main


def _add_worktree(main: Path, tmp_path: Path) -> Path:
    worktree = tmp_path / "linked-wt"
    _git(["worktree", "add", "-b", "wt-branch", str(worktree)], main)
    return worktree


def test_regular_checkout_returns_none(tmp_path: Path) -> None:
    main = _make_repo(tmp_path)
    assert resolve_worktree_main_root(main) is None
    assert resolve_worktree_main_root(main / ".git") is None


def test_non_git_path_returns_none(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert resolve_worktree_main_root(plain) is None


def test_worktree_resolves_to_main_root(tmp_path: Path) -> None:
    main = _make_repo(tmp_path)
    worktree = _add_worktree(main, tmp_path)
    assert resolve_worktree_main_root(worktree) == str(main.resolve())


def test_worktree_subdirectory_resolves_to_main_root(tmp_path: Path) -> None:
    main = _make_repo(tmp_path)
    worktree = _add_worktree(main, tmp_path)
    nested = worktree / "pkg" / "deep"
    nested.mkdir(parents=True)
    assert resolve_worktree_main_root(nested) == str(main.resolve())


def test_resolve_project_root_shares_worktree(tmp_path: Path, monkeypatch) -> None:
    main = _make_repo(tmp_path)
    worktree = _add_worktree(main, tmp_path)
    monkeypatch.setattr(root_tasks, "WORKTREE_SHARED_ROOT", True)
    assert root_tasks.resolve_project_root(str(worktree)) == str(main.resolve())


def test_resolve_project_root_worktree_opt_out(tmp_path: Path, monkeypatch) -> None:
    main = _make_repo(tmp_path)
    worktree = _add_worktree(main, tmp_path)
    monkeypatch.setattr(root_tasks, "WORKTREE_SHARED_ROOT", False)
    assert root_tasks.resolve_project_root(str(worktree)) == str(worktree.resolve())
