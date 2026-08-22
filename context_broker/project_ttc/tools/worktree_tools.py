"""Git worktree detection and main-checkout resolution helpers.

Linked git worktrees carry a `.git` *file* (gitfile) instead of a directory.
The gitfile points at `<main>/.git/worktrees/<name>`, and that gitdir contains
a `commondir` file pointing back at the shared git directory. The main
repository checkout is the parent of that shared git directory, so every
worktree of a repo can resolve to one canonical project root and share its
index, caches, and storage digest.
"""

from pathlib import Path
from typing import Optional


def _parse_gitfile(git_file: Path) -> Optional[Path]:
    """Parse a `.git` gitfile and return the absolute gitdir it references."""
    try:
        text = git_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    raw = text[len("gitdir:") :].strip()
    if not raw:
        return None
    gitdir = Path(raw)
    if not gitdir.is_absolute():
        gitdir = git_file.parent / gitdir
    try:
        return gitdir.resolve()
    except OSError:
        return None


def _common_git_dir(gitdir: Path) -> Optional[Path]:
    """Return the shared git directory for a worktree gitdir, if any."""
    commondir_file = gitdir / "commondir"
    if commondir_file.is_file():
        try:
            raw = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None
        if raw:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = gitdir / candidate
            try:
                return candidate.resolve()
            except OSError:
                return None
    # Fallback: linked-worktree gitdirs live at <common>/worktrees/<name>.
    if gitdir.parent.name == "worktrees":
        return gitdir.parent.parent
    return None


def resolve_worktree_main_root(path: str | Path) -> Optional[str]:
    """Return the main checkout root when *path* is inside a linked git worktree.

    Walks up from *path* to the nearest `.git` marker: a directory means a
    regular checkout (returns None); a gitfile means a linked worktree, whose
    main checkout root is derived from the shared git directory. Returns None
    for non-git paths and worktrees whose main checkout cannot be verified.
    """
    try:
        current = Path(path).resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent

    while True:
        git_marker = current / ".git"
        if git_marker.is_dir():
            return None
        if git_marker.is_file():
            gitdir = _parse_gitfile(git_marker)
            if gitdir is None:
                return None
            common = _common_git_dir(gitdir)
            if common is None:
                return None
            main_root = common.parent
            try:
                resolved_main = main_root.resolve()
            except OSError:
                return None
            if resolved_main == current or not resolved_main.is_dir():
                return None
            if not (resolved_main / ".git").exists():
                return None
            return str(resolved_main)
        if current == current.parent:
            return None
        current = current.parent
