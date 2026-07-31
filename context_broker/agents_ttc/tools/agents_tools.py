"""Helpers for AGENTS.md generation and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from context_broker.utils import log


AGENTS_MD_FILENAME = "AGENTS.md"

REQUIRED_SECTIONS = [
    "project goal",
    "goals",
    "objectives",
    "purpose",
    "mission",
    "about",
    "overview",
    "description",
]

OPTIONAL_SECTIONS = [
    "tech stack",
    "technology",
    "architecture",
    "coding conventions",
    "style guide",
    "testing",
    "deployment",
    "contributing",
    "dependencies",
    "project structure",
    "directory structure",
]


def find_agents_md(project_root: str | Path) -> Path | None:
    """Find AGENTS.md in project root (case-insensitive)."""
    root = Path(project_root)
    for name in ("AGENTS.md", "agents.md", "Agents.md"):
        path = root / name
        if path.exists():
            return path
    return None


def has_agents_md(project_root: str | Path) -> bool:
    """Check if project has an AGENTS.md file."""
    return find_agents_md(project_root) is not None


def read_agents_md(project_root: str | Path) -> str:
    """Read AGENTS.md content, returning empty string if missing."""
    path = find_agents_md(project_root)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log(f"⚠️ Error reading AGENTS.md: {e}", "WARN")
        return ""


def write_agents_md(project_root: str | Path, content: str) -> Path:
    """Write AGENTS.md to project root."""
    root = Path(project_root)
    path = root / AGENTS_MD_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


def extract_project_metadata(project_root: str | Path) -> dict[str, Any]:
    """Extract project metadata from common project files."""
    root = Path(project_root)
    metadata: dict[str, Any] = {
        "name": root.name,
        "description": "",
        "version": "",
        "tech_stack": [],
        "entry_points": [],
        "dependencies": [],
        "authors": [],
        "license": "",
    }

    # README.md
    readme = _find_file_case_insensitive(root, "README.md")
    if readme:
        content = _safe_read(readme, 5000)
        metadata["description"] = _extract_first_paragraph(content)

    # Python: pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        metadata["tech_stack"].append("Python")
        _parse_pyproject(pyproject, metadata)

    # Python: requirements.txt
    requirements = root / "requirements.txt"
    if requirements.exists():
        metadata["tech_stack"].append("Python")
        deps = _safe_read(requirements, 2000).splitlines()
        metadata["dependencies"].extend(d.strip() for d in deps if d.strip() and not d.startswith("#"))

    # Node.js: package.json
    package_json = root / "package.json"
    if package_json.exists():
        metadata["tech_stack"].append("Node.js")
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            metadata["description"] = metadata["description"] or data.get("description", "")
            metadata["version"] = metadata["version"] or data.get("version", "")
            metadata["dependencies"].extend(data.get("dependencies", {}).keys())
            metadata["entry_points"].append(data.get("main", ""))
        except Exception:
            pass

    # Rust: Cargo.toml
    cargo = root / "Cargo.toml"
    if cargo.exists():
        metadata["tech_stack"].append("Rust")
        content = _safe_read(cargo, 2000)
        metadata["description"] = metadata["description"] or _extract_toml_value(content, "description")
        metadata["version"] = metadata["version"] or _extract_toml_value(content, "version")

    # Go: go.mod
    gomod = root / "go.mod"
    if gomod.exists():
        metadata["tech_stack"].append("Go")
        content = _safe_read(gomod, 2000)
        for line in content.splitlines():
            if line.startswith("module "):
                metadata["name"] = line.split()[1].split("/")[-1]
                break

    # Java: pom.xml
    pom = root / "pom.xml"
    if pom.exists():
        metadata["tech_stack"].append("Java (Maven)")

    # Java: build.gradle
    gradle = root / "build.gradle"
    if gradle.exists():
        metadata["tech_stack"].append("Java (Gradle)")

    # Dockerfile
    dockerfile = _find_file_case_insensitive(root, "Dockerfile")
    if dockerfile:
        metadata["tech_stack"].append("Docker")

    # Makefile
    makefile = _find_file_case_insensitive(root, "Makefile")
    if makefile:
        metadata["tech_stack"].append("Make")

    # LICENSE
    license_file = _find_file_case_insensitive(root, "LICENSE")
    if license_file:
        metadata["license"] = license_file.name

    # Deduplicate and clean
    metadata["tech_stack"] = list(dict.fromkeys(metadata["tech_stack"]))
    metadata["entry_points"] = [ep for ep in metadata["entry_points"] if ep]
    metadata["dependencies"] = list(dict.fromkeys(metadata["dependencies"]))[:20]

    return metadata


def generate_agents_md_content(metadata: dict[str, Any]) -> str:
    """Generate AGENTS.md content from project metadata."""
    lines = [
        "# Agent Instructions",
        "",
        f"## Project: {metadata.get('name', 'Unknown')}",
        "",
        "## Project Goals",
        "",
    ]

    description = metadata.get("description", "")
    if description:
        lines.append(description)
        lines.append("")
    else:
        lines.append("<!-- Add a clear description of what this project aims to achieve. -->")
        lines.append("")

    lines.extend([
        "## Overview",
        "",
        f"- **Name**: {metadata.get('name', 'Unknown')}",
    ])

    version = metadata.get("version", "")
    if version:
        lines.append(f"- **Version**: {version}")

    if metadata.get("license"):
        lines.append(f"- **License**: {metadata['license']}")

    lines.append("")

    if metadata.get("tech_stack"):
        lines.extend([
            "## Tech Stack",
            "",
        ])
        for tech in metadata["tech_stack"]:
            lines.append(f"- {tech}")
        lines.append("")

    if metadata.get("entry_points"):
        lines.extend([
            "## Entry Points",
            "",
        ])
        for ep in metadata["entry_points"]:
            lines.append(f"- `{ep}`")
        lines.append("")

    if metadata.get("dependencies"):
        lines.extend([
            "## Key Dependencies",
            "",
        ])
        for dep in metadata["dependencies"][:15]:
            lines.append(f"- {dep}")
        lines.append("")

    lines.extend([
        "## Architecture & Conventions",
        "",
        "<!-- Describe the project's architecture, coding conventions, and important patterns. -->",
        "",
        "## Testing",
        "",
        "<!-- Describe how to run tests and what testing framework is used. -->",
        "",
        "## Deployment",
        "",
        "<!-- Describe how the project is built and deployed. -->",
        "",
    ])

    return "\n".join(lines)


def validate_agents_md_content(content: str) -> dict[str, Any]:
    """Validate AGENTS.md content and report missing sections."""
    result: dict[str, Any] = {
        "exists": bool(content),
        "has_goals": False,
        "missing_required": [],
        "missing_optional": [],
        "suggestions": [],
        "score": 0,
    }

    if not content:
        result["missing_required"] = ["File does not exist"]
        result["suggestions"].append("Create an AGENTS.md file at the project root.")
        return result

    lower = content.lower()

    # Check for goals section
    for section in REQUIRED_SECTIONS:
        if section in lower:
            result["has_goals"] = True
            break

    if not result["has_goals"]:
        result["missing_required"].append("Project Goals / Purpose / Overview section")
        result["suggestions"].append("Add a 'Project Goals' section describing what the project aims to achieve.")

    # Check for optional sections
    found_optional = 0
    for section in OPTIONAL_SECTIONS:
        if section in lower:
            found_optional += 1
        else:
            result["missing_optional"].append(section.title())

    # Score: 50 for having goals, plus up to 50 for optional sections
    result["score"] = 50 if result["has_goals"] else 0
    result["score"] += min(50, found_optional * 5)

    if result["score"] < 30:
        result["suggestions"].append("AGENTS.md is very sparse. Consider adding more context about the project.")
    elif result["score"] < 60:
        result["suggestions"].append("AGENTS.md has basic info but could be expanded with architecture and conventions.")

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_file_case_insensitive(root: Path, name: str) -> Path | None:
    """Find a file case-insensitively in the given directory."""
    for entry in root.iterdir():
        if entry.is_file() and entry.name.lower() == name.lower():
            return entry
    return None


def _safe_read(path: Path, max_chars: int = 5000) -> str:
    """Safely read a file with a character limit."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception as e:
        log(f"⚠️ Error reading {path}: {e}", "WARN")
        return ""


def _extract_first_paragraph(text: str) -> str:
    """Extract the first non-empty paragraph from markdown text."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith("#"):
            continue
        lines.append(stripped)
    return " ".join(lines)[:500]


def _extract_toml_value(text: str, key: str) -> str:
    """Extract a simple string value from TOML-like content."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f'{key} = '):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value
    return ""


def _parse_pyproject(path: Path, metadata: dict[str, Any]) -> None:
    """Parse pyproject.toml for metadata."""
    content = _safe_read(path, 3000)
    metadata["version"] = metadata["version"] or _extract_toml_value(content, "version")
    desc = _extract_toml_value(content, "description")
    if desc:
        metadata["description"] = metadata["description"] or desc
    # Try to find dependencies in [project] section
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies") and "[" in stripped:
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("]"):
                in_deps = False
                continue
            dep = stripped.strip().strip(',').strip('"').strip("'")
            if dep and not dep.startswith("#"):
                metadata["dependencies"].append(dep.split("[")[0].split("=")[0].strip())
