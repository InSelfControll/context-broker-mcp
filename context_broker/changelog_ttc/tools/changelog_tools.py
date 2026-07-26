"""
Changelog generation and management tools.

Parses git commits, categorizes changes, and generates structured
CHANGELOG.md entries following Keep a Changelog conventions.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from context_broker.utils import log


COMMIT_TYPE_EMOJI: dict[str, str] = {
    "feat": "✨",
    "fix": "🐛",
    "security": "🔒",
    "perf": "⚡",
    "refactor": "♻️",
    "docs": "📝",
    "style": "💄",
    "test": "✅",
    "chore": "🔧",
    "ci": "🚀",
    "build": "📦",
    "revert": "⏪",
    "deps": "📌",
}

COMMIT_TYPE_LABEL: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "security": "Security",
    "perf": "Performance",
    "refactor": "Changed",
    "docs": "Documentation",
    "style": "Changed",
    "test": "Testing",
    "chore": "Chore",
    "ci": "CI/CD",
    "build": "Build",
    "revert": "Reverted",
    "deps": "Dependencies",
}

SEPARATOR_LINE = "---\n"


@dataclass
class ParsedCommit:
    """A parsed git commit ready for changelog inclusion."""

    hash: str
    short_hash: str
    subject: str
    body: str
    author: str
    date: str
    commit_type: str
    scope: str
    is_breaking: bool
    is_merge: bool
    pr_number: Optional[str] = None


def _run_git(args: list[str], cwd: str = ".") -> str:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log(f"⚠️ Git command failed: {' '.join(args)} — {e.stderr}", "WARN")
        return ""
    except FileNotFoundError:
        log("⚠️ Git not found in PATH", "WARN")
        return ""


def _parse_commit_message(subject: str) -> tuple[str, str, bool]:
    """Parse a conventional commit subject line.

    Returns:
        (commit_type, scope, is_breaking) tuple.
    """
    # Check for BREAKING CHANGE anywhere in the subject first
    is_breaking = "BREAKING CHANGE" in subject.upper()

    # Pattern: type(scope)!: subject or type!: subject or type: subject
    pattern = r"^(\w+)(?:\(([^)]+)\))?(!)?\s*:\s*(.*)$"
    match = re.match(pattern, subject)
    if match:
        commit_type = match.group(1).lower()
        scope = match.group(2) or ""
        # Also check for explicit breaking flag
        is_breaking = is_breaking or (match.group(3) == "!")
        return commit_type, scope, is_breaking

    return "", "", is_breaking


def parse_git_commits(
    since: str = "",
    until: str = "HEAD",
    cwd: str = ".",
    max_count: int = 200,
) -> list[ParsedCommit]:
    """Parse git commits into structured changelog entries.

    Args:
        since: Commit hash or tag to start from (empty = all history).
        until: Commit hash or tag to end at (default: HEAD).
        cwd: Working directory for git commands.
        max_count: Maximum commits to parse.

    Returns:
        List of ParsedCommit objects.
    """
    format_str = "%H%n%h%n%s%n%b%n%aN%n%aI%n---COMMIT_END---"
    args = ["log", f"--format={format_str}"]

    if since:
        args.append(f"{since}..{until}")
    else:
        args.append(f"-{max_count}")

    output = _run_git(args, cwd=cwd)
    if not output:
        return []

    commits: list[ParsedCommit] = []
    raw_commits = output.split("---COMMIT_END---")

    for raw in raw_commits:
        lines = raw.strip().splitlines()
        if len(lines) < 5:
            continue

        commit_hash = lines[0]
        short_hash = lines[1]
        subject = lines[2]
        body = "\n".join(lines[3:-2])
        author = lines[-2]
        date = lines[-1]

        # Skip merge commits without meaningful content
        is_merge = subject.startswith("Merge pull request") or subject.startswith("Merge branch")

        commit_type, scope, is_breaking = _parse_commit_message(subject)

        # Extract PR number from merge commits
        pr_number = None
        pr_match = re.search(r"#(\d+)", subject)
        if pr_match:
            pr_number = pr_match.group(1)

        commits.append(
            ParsedCommit(
                hash=commit_hash,
                short_hash=short_hash,
                subject=subject,
                body=body,
                author=author,
                date=date,
                commit_type=commit_type,
                scope=scope,
                is_breaking=is_breaking,
                is_merge=is_merge,
                pr_number=pr_number,
            )
        )

    return commits


def _changes_only_changelog(commit_hash: str, cwd: str) -> bool:
    """Return whether a commit changes only the root CHANGELOG.md file."""
    output = _run_git(
        [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit_hash,
        ],
        cwd=cwd,
    )
    changed_paths = {
        path.removeprefix("./")
        for path in output.splitlines()
        if path.strip()
    }
    return changed_paths == {"CHANGELOG.md"}


def categorize_commits(commits: list[ParsedCommit]) -> dict[str, list[ParsedCommit]]:
    """Group commits by their changelog category.

    Returns:
        Dict mapping category label to list of commits.
    """
    categories: dict[str, list[ParsedCommit]] = {
        "Added": [],
        "Fixed": [],
        "Security": [],
        "Changed": [],
        "Performance": [],
        "Documentation": [],
        "Testing": [],
        "Dependencies": [],
        "CI/CD": [],
        "Build": [],
        "Reverted": [],
        "Chore": [],
        "Uncategorized": [],
    }

    for commit in commits:
        if commit.is_merge and not commit.pr_number:
            # Skip plain merge commits without PR reference
            continue

        label = COMMIT_TYPE_LABEL.get(commit.commit_type, "Uncategorized")
        categories[label].append(commit)

    return {k: v for k, v in categories.items() if v}


def format_changelog_entry(commit: ParsedCommit) -> str:
    """Format a single commit as a changelog bullet."""
    emoji = COMMIT_TYPE_EMOJI.get(commit.commit_type, "📝")
    breaking = " **[BREAKING]**" if commit.is_breaking else ""

    # Clean up subject: remove conventional commit prefix
    clean_subject = commit.subject
    prefix_pattern = r"^\w+(?:\([^)]+\))?(!)?\s*:\s*"
    clean_subject = re.sub(prefix_pattern, "", clean_subject)

    # Add PR link if available
    pr_ref = ""
    if commit.pr_number:
        pr_ref = f" ([#{commit.pr_number}](https://github.com/yourusername/context-broker-mcp/pull/{commit.pr_number}))"

    line = f"- {emoji} {clean_subject}{breaking}{pr_ref} — `{commit.short_hash}`"
    return line


def generate_changelog_section(
    version: str,
    commits: list[ParsedCommit],
    date: Optional[str] = None,
) -> str:
    """Generate a changelog section for a release.

    Args:
        version: Version string (e.g., "0.2.0" or "Unreleased").
        commits: List of commits to include.
        date: Release date (default: today).

    Returns:
        Formatted changelog section as a string.
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [f"## [{version}] — {date}", ""]

    categories = categorize_commits(commits)

    for category, cat_commits in categories.items():
        lines.append(f"### {category}")
        lines.append("")
        for commit in cat_commits:
            lines.append(format_changelog_entry(commit))
        lines.append("")

    return "\n".join(lines)


def find_latest_changelog_version(changelog_path: str | Path) -> tuple[str, str]:
    """Find the latest version and its first commit hash from CHANGELOG.md.

    Returns:
        (version, first_commit_hash) tuple. Empty strings if not found.
    """
    path = Path(changelog_path)
    if not path.exists():
        return "", ""

    content = path.read_text(encoding="utf-8")

    # Find version header like "## [0.1.0] — 2024-01-15"
    version_match = re.search(r"## \[([^\]]+)\]", content)
    if not version_match:
        return "", ""

    version = version_match.group(1)

    # Find first commit hash in that section
    hash_match = re.search(r"`([a-f0-9]{7,})`", content)
    if hash_match:
        return version, hash_match.group(1)

    return version, ""


def update_changelog(
    changelog_path: str | Path,
    version: str = "Unreleased",
    since: str = "",
    cwd: str = ".",
) -> dict[str, str]:
    """Update CHANGELOG.md with new entries from git commits.

    Args:
        changelog_path: Path to CHANGELOG.md.
        version: Version label for the new section.
        since: Git ref to start from (auto-detected from CHANGELOG if empty).
        cwd: Working directory.

    Returns:
        Dict with status, message, and generated content.
    """
    path = Path(changelog_path)

    # Auto-detect since ref from existing CHANGELOG
    if not since and path.exists():
        _, since = find_latest_changelog_version(path)

    commits = parse_git_commits(since=since, cwd=cwd)
    if not commits:
        return {
            "status": "no_changes",
            "message": "No new commits found since last changelog update.",
            "content": "",
            "commit_count": "0",
        }

    new_section = generate_changelog_section(version, commits)

    # Read existing content
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = _default_changelog_header()

    # Insert new section after the header (before first ##)
    insert_pos = existing.find("## ")
    if insert_pos >= 0:
        updated = existing[:insert_pos] + new_section + "\n" + existing[insert_pos:]
    else:
        updated = existing + "\n" + new_section + "\n"

    path.write_text(updated, encoding="utf-8")

    categories = categorize_commits(commits)
    summary = ", ".join(f"{k}: {len(v)}" for k, v in categories.items())

    log(f"📝 Updated CHANGELOG.md with {len(commits)} commits ({summary})")

    return {
        "status": "updated",
        "message": f"Updated CHANGELOG.md with {len(commits)} commits.",
        "content": new_section,
        "commit_count": str(len(commits)),
        "categories": summary,
    }


def validate_changelog(changelog_path: str | Path) -> dict[str, str | bool]:
    """Validate that CHANGELOG.md is up to date with git history.

    Returns:
        Dict with validation results.
    """
    path = Path(changelog_path)
    if not path.exists():
        return {
            "status": "missing",
            "valid": False,
            "message": "CHANGELOG.md does not exist.",
        }

    version, since = find_latest_changelog_version(path)
    commits = parse_git_commits(since=since, cwd=str(path.parent))

    # Filter out merges and already-documented commits
    undocumented = [
        commit
        for commit in commits
        if (not commit.is_merge or commit.pr_number)
        and not _changes_only_changelog(commit.hash, str(path.parent))
    ]

    if not undocumented:
        return {
            "status": "up_to_date",
            "valid": True,
            "message": "CHANGELOG.md is up to date with git history.",
            "missing_count": 0,
        }

    return {
        "status": "outdated",
        "valid": False,
        "message": f"{len(undocumented)} commits are not documented in CHANGELOG.md.",
        "missing_count": len(undocumented),
        "latest_version": version,
        "suggestion": f"Run changelog update to document {len(undocumented)} missing commits.",
    }


def _default_changelog_header() -> str:
    """Return the default CHANGELOG.md header."""
    return """# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""


def get_changelog_summary(changelog_path: str | Path) -> dict[str, str]:
    """Get a summary of the current changelog state."""
    path = Path(changelog_path)
    if not path.exists():
        return {"status": "missing", "versions": "0", "latest_version": "", "total_entries": "0"}

    content = path.read_text(encoding="utf-8")
    versions = re.findall(r"## \[([^\]]+)\]", content)
    entries = len(re.findall(r"^- ", content, re.MULTILINE))

    return {
        "status": "exists",
        "versions": str(len(versions)),
        "latest_version": versions[0] if versions else "",
        "total_entries": str(entries),
    }
