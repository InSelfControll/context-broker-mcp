"""
Documentation generation tools for auto-creating feature docs.

Creates docs/{feature}/{feature}-{fix-type}.md for new changes,
or docs/{feature}/{fix-type}.md if no related docs exist yet.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from context_broker.changelog_ttc.tools.changelog_tools import (
    COMMIT_TYPE_EMOJI,
    COMMIT_TYPE_LABEL,
    _parse_commit_message,
)
from context_broker.utils import log


# Feature detection: map file paths / scopes to feature names
FEATURE_PATH_PATTERNS: dict[str, str] = {
    "agents_ttc": "agents",
    "agents.py": "agents",
    "security_ttc": "security",
    "changelog_ttc": "changelog",
    "server_ttc": "server",
    "indexer_ttc": "indexer",
    "storage_ttc": "storage",
    "project_ttc": "project",
    "config.py": "config",
    "lifecycle.py": "lifecycle",
    "README.md": "readme",
    "CONTRIBUTING.md": "contributing",
    "ARCHITECTURE.md": "architecture",
    "tests/": "testing",
    "pyproject.toml": "build",
    "Dockerfile": "deployment",
    ".github/": "ci",
}


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
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _infer_feature_from_scope(scope: str) -> str:
    """Normalize commit scope to feature name."""
    scope_lower = scope.lower().strip()
    # Direct mapping
    if scope_lower in FEATURE_PATH_PATTERNS:
        return FEATURE_PATH_PATTERNS[scope_lower]
    # Check if scope contains a known feature keyword
    for pattern, feature in FEATURE_PATH_PATTERNS.items():
        if pattern.replace("_ttc", "") in scope_lower or feature in scope_lower:
            return feature
    return scope_lower


def _infer_feature_from_files(files: list[str]) -> str:
    """Infer feature name from changed file paths."""
    for file in files:
        file_lower = file.lower()
        for pattern, feature in FEATURE_PATH_PATTERNS.items():
            if pattern.lower() in file_lower:
                return feature
    return "general"


def _get_changed_files(commit_hash: str, cwd: str = ".") -> list[str]:
    """Get list of files changed in a commit."""
    output = _run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash], cwd)
    if not output:
        return []
    return [f.strip() for f in output.splitlines() if f.strip()]


def _get_recent_commits(since: str = "", max_count: int = 50, cwd: str = ".") -> list[dict[str, Any]]:
    """Get recent commits with their details."""
    format_str = "%H%n%s%n%b%n%aN%n%aI%n---END---"
    args = ["log", f"--format={format_str}"]
    if since:
        args.append(f"{since}..HEAD")
    else:
        args.append(f"-{max_count}")

    output = _run_git(args, cwd)
    if not output:
        return []

    commits = []
    for raw in output.split("---END---"):
        lines = raw.strip().splitlines()
        if len(lines) < 5:
            continue
        commit_hash = lines[0]
        subject = lines[1]
        body = "\n".join(lines[2:-2])
        commit_type, scope, is_breaking = _parse_commit_message(subject)
        files = _get_changed_files(commit_hash, cwd)

        # Determine feature
        feature = ""
        if scope:
            feature = _infer_feature_from_scope(scope)
        if not feature or feature == "general":
            feature = _infer_feature_from_files(files)

        # Clean subject
        clean_subject = re.sub(r"^\w+(?:\([^)]+\))?(!)?\s*:\s*", "", subject)

        commits.append({
            "hash": commit_hash[:7],
            "subject": clean_subject,
            "full_subject": subject,
            "body": body.strip(),
            "type": commit_type,
            "scope": scope,
            "feature": feature,
            "is_breaking": is_breaking,
            "files": files,
        })

    return commits


def _has_existing_feature_docs(docs_dir: Path, feature: str) -> bool:
    """Check if docs/{feature}/ directory already has any .md files."""
    feature_dir = docs_dir / feature
    if not feature_dir.exists():
        return False
    return any(feature_dir.iterdir()) and any(f.suffix == ".md" for f in feature_dir.iterdir())


def _determine_doc_filename(docs_dir: Path, feature: str, fix_type: str) -> Path:
    """Determine the doc filename based on whether related docs exist.

    Rules:
    - If docs/{feature}/ has NO .md files: docs/{feature}/{fix_type}.md
    - If docs/{feature}/ HAS .md files: docs/{feature}/{feature}-{fix_type}.md
    """
    feature_dir = docs_dir / feature
    feature_dir.mkdir(parents=True, exist_ok=True)

    has_existing = _has_existing_feature_docs(docs_dir, feature)

    if has_existing:
        filename = f"{feature}-{fix_type}.md"
    else:
        filename = f"{fix_type}.md"

    return feature_dir / filename


def _generate_doc_content(
    feature: str,
    fix_type: str,
    commits: list[dict[str, Any]],
    project_name: str = "",
) -> str:
    """Generate documentation content for a feature+fix-type."""
    emoji = COMMIT_TYPE_EMOJI.get(fix_type, "📝")
    label = COMMIT_TYPE_LABEL.get(fix_type, "Changes")

    lines = [
        f"# {emoji} {feature.title()} — {label}",
        "",
        f"This document covers {label.lower()} related to the **{feature}** feature.",
        "",
        "## Overview",
        "",
        f"The following changes were made to {feature}:",
        "",
    ]

    for commit in commits:
        lines.append(f"- **{commit['hash']}**: {commit['subject']}")
        if commit["files"]:
            files_str = ", ".join(f"`{f}`" for f in commit["files"][:5])
            if len(commit["files"]) > 5:
                files_str += f" and {len(commit['files']) - 5} more"
            lines.append(f"  - Files: {files_str}")
        if commit["body"]:
            # Add first line of body as detail
            body_first = commit["body"].splitlines()[0].strip()
            if body_first and body_first != commit["subject"]:
                lines.append(f"  - Detail: {body_first}")
        lines.append("")

    # Add breaking changes section if any
    breaking = [c for c in commits if c["is_breaking"]]
    if breaking:
        lines.extend([
            "## ⚠ Breaking Changes",
            "",
        ])
        for commit in breaking:
            lines.append(f"- **{commit['hash']}**: {commit['subject']}")
        lines.append("")

    lines.extend([
        "## Related Files",
        "",
    ])

    all_files: set[str] = set()
    for commit in commits:
        all_files.update(commit["files"])

    for f in sorted(all_files)[:20]:
        lines.append(f"- `{f}`")
    if len(all_files) > 20:
        lines.append(f"- ... and {len(all_files) - 20} more files")

    lines.extend([
        "",
        "---",
        "",
        "*This document was auto-generated from git commit history.*",
    ])

    return "\n".join(lines)


def generate_feature_docs(
    project_root: str,
    since: str = "",
    max_count: int = 50,
) -> list[dict[str, Any]]:
    """Generate documentation for all recent feature changes.

    Args:
        project_root: Project root path.
        since: Git ref to start from (default: last 50 commits).
        max_count: Max commits to analyze.

    Returns:
        List of dicts with created/updated doc info.
    """
    root = Path(project_root).resolve()
    docs_dir = root / "docs"
    docs_dir.mkdir(exist_ok=True)

    commits = _get_recent_commits(since=since, max_count=max_count, cwd=str(root))
    if not commits:
        log("ℹ No commits found to document.")
        return []

    # Group commits by (feature, type)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for commit in commits:
        feature = commit["feature"]
        fix_type = commit["type"] or "uncategorized"
        key = (feature, fix_type)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(commit)

    results: list[dict[str, Any]] = []

    for (feature, fix_type), feature_commits in grouped.items():
        doc_path = _determine_doc_filename(docs_dir, feature, fix_type)

        # Check if doc already exists (check both naming conventions)
        feature_dir = docs_dir / feature
        existing_paths = [
            feature_dir / f"{feature}-{fix_type}.md",
            feature_dir / f"{fix_type}.md",
        ]
        existing_doc = next((p for p in existing_paths if p.exists()), None)
        if existing_doc:
            log(f"📄 Doc already exists: {existing_doc}")
            results.append({
                "feature": feature,
                "fix_type": fix_type,
                "path": str(existing_doc),
                "status": "exists",
                "created": False,
                "message": f"Doc already exists at {existing_doc}",
            })
            continue

        content = _generate_doc_content(feature, fix_type, feature_commits)
        doc_path.write_text(content, encoding="utf-8")

        log(f"📝 Created doc: {doc_path} ({len(feature_commits)} commits)")
        results.append({
            "feature": feature,
            "fix_type": fix_type,
            "path": str(doc_path),
            "status": "created",
            "created": True,
            "commit_count": len(feature_commits),
            "message": f"Created {doc_path} with {len(feature_commits)} commits",
        })

    return results


def ensure_feature_docs(
    project_root: str,
    since: str = "",
    max_count: int = 50,
) -> dict[str, Any]:
    """Ensure documentation exists for all recent feature changes.

    Returns:
        Dict with summary of created docs.
    """
    root = Path(project_root).resolve()
    log(f"📝 Ensuring feature docs for {root.name}...")

    results = generate_feature_docs(str(root), since=since, max_count=max_count)

    created = [r for r in results if r["status"] == "created"]
    existing = [r for r in results if r["status"] == "exists"]

    if not results:
        return {
            "status": "no_changes",
            "message": "No commits found to document.",
            "created_count": 0,
            "existing_count": 0,
            "docs": [],
        }

    return {
        "status": "updated" if created else "no_new",
        "message": f"Created {len(created)} docs, {len(existing)} already exist.",
        "created_count": len(created),
        "existing_count": len(existing),
        "docs": results,
    }


def scan_for_missing_docs(project_root: str, since: str = "", max_count: int = 50) -> dict[str, Any]:
    """Scan for feature changes that are missing documentation.

    Returns:
        Dict with missing docs report.
    """
    root = Path(project_root).resolve()
    docs_dir = root / "docs"

    commits = _get_recent_commits(since=since, max_count=max_count, cwd=str(root))
    if not commits:
        return {"status": "no_commits", "missing": [], "message": "No commits found."}

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for commit in commits:
        key = (commit["feature"], commit["type"] or "uncategorized")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(commit)

    missing: list[dict[str, Any]] = []
    for (feature, fix_type), feature_commits in grouped.items():
        feature_dir = docs_dir / feature
        existing_paths = [
            feature_dir / f"{feature}-{fix_type}.md",
            feature_dir / f"{fix_type}.md",
        ]
        if not any(p.exists() for p in existing_paths):
            suggested = _determine_doc_filename(docs_dir, feature, fix_type)
            missing.append({
                "feature": feature,
                "fix_type": fix_type,
                "commits": len(feature_commits),
                "suggested_path": str(suggested),
            })

    return {
        "status": "missing" if missing else "complete",
        "missing_count": len(missing),
        "message": f"{len(missing)} feature doc(s) missing." if missing else "All feature changes are documented.",
        "missing": missing,
    }


def get_docs_summary(project_root: str) -> dict[str, Any]:
    """Get summary of all feature docs.

    Returns:
        Dict with docs statistics.
    """
    root = Path(project_root).resolve()
    docs_dir = root / "docs"

    if not docs_dir.exists():
        return {"status": "missing", "features": 0, "total_docs": 0, "features_list": []}

    features = [d.name for d in docs_dir.iterdir() if d.is_dir()]
    total_docs = sum(len(list((docs_dir / f).glob("*.md"))) for f in features)

    return {
        "status": "exists",
        "features": len(features),
        "total_docs": total_docs,
        "features_list": features,
    }
