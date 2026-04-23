"""Tests for AGENTS.md management module."""

from pathlib import Path

import pytest

from context_broker.agents_ttc.tasks.agents_tasks import (
    ensure_agents_md,
    generate_agents_md,
    scan_for_missing_agents_md,
    validate_agents_md,
)
from context_broker.agents_ttc.tools.agents_tools import (
    extract_project_metadata,
    generate_agents_md_content,
    has_agents_md,
    validate_agents_md_content,
)


class TestAgentsTools:
    """Tests for agents_tools helpers."""

    def test_has_agents_md_missing(self, tmp_path: Path) -> None:
        assert has_agents_md(tmp_path) is False

    def test_has_agents_md_present(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Test")
        assert has_agents_md(tmp_path) is True

    def test_has_agents_md_case_insensitive(self, tmp_path: Path) -> None:
        (tmp_path / "agents.md").write_text("# Test")
        assert has_agents_md(tmp_path) is True

    def test_extract_project_metadata_empty(self, tmp_path: Path) -> None:
        metadata = extract_project_metadata(tmp_path)
        assert metadata["name"] == tmp_path.name
        assert metadata["description"] == ""
        assert metadata["tech_stack"] == []

    def test_extract_project_metadata_with_readme(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# My Project\n\nA cool project.\n")
        metadata = extract_project_metadata(tmp_path)
        assert "My Project" in metadata["description"] or "A cool project" in metadata["description"]

    def test_extract_project_metadata_nodejs(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "test-app", "description": "Test app", "version": "1.0.0", "main": "index.js"}'
        )
        metadata = extract_project_metadata(tmp_path)
        assert "Node.js" in metadata["tech_stack"]
        assert metadata["version"] == "1.0.0"
        assert "index.js" in metadata["entry_points"]

    def test_extract_project_metadata_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-lib"\nversion = "0.2.0"\ndescription = "A test lib"\n'
        )
        metadata = extract_project_metadata(tmp_path)
        assert "Python" in metadata["tech_stack"]
        assert metadata["version"] == "0.2.0"

    def test_generate_agents_md_content(self) -> None:
        metadata = {
            "name": "demo",
            "description": "A demo project.",
            "version": "1.0.0",
            "tech_stack": ["Python", "Docker"],
            "entry_points": ["main.py"],
            "dependencies": ["fastmcp", "numpy"],
            "license": "MIT",
        }
        content = generate_agents_md_content(metadata)
        assert "# Agent Instructions" in content
        assert "## Project Goals" in content
        assert "A demo project." in content
        assert "Python" in content
        assert "Docker" in content
        assert "main.py" in content
        assert "fastmcp" in content
        assert "MIT" in content

    def test_validate_agents_md_content_missing(self) -> None:
        result = validate_agents_md_content("")
        assert result["exists"] is False
        assert result["has_goals"] is False
        assert result["score"] == 0

    def test_validate_agents_md_content_valid(self) -> None:
        content = "# Agent Instructions\n\n## Project Goals\n\nDo things.\n\n## Tech Stack\n\n- Python\n"
        result = validate_agents_md_content(content)
        assert result["exists"] is True
        assert result["has_goals"] is True
        assert result["score"] >= 50

    def test_validate_agents_md_content_needs_work(self) -> None:
        content = "# Agent Instructions\n\nSome text.\n"
        result = validate_agents_md_content(content)
        assert result["exists"] is True
        assert result["has_goals"] is False
        assert result["score"] == 0


class TestAgentsTasks:
    """Tests for high-level agents tasks."""

    def test_ensure_agents_md_creates_file(self, tmp_path: Path) -> None:
        result = ensure_agents_md(str(tmp_path))
        assert result["status"] == "created"
        assert result["created"] is True
        assert (tmp_path / "AGENTS.md").exists()

    def test_ensure_agents_md_existing(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Existing")
        result = ensure_agents_md(str(tmp_path))
        assert result["status"] == "exists"
        assert result["created"] is False

    def test_validate_agents_md_missing(self, tmp_path: Path) -> None:
        result = validate_agents_md(str(tmp_path))
        assert result["status"] == "missing"
        assert result["valid"] is False

    def test_validate_agents_md_valid(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Agent Instructions\n\n## Project Goals\n\nDo things.\n")
        result = validate_agents_md(str(tmp_path))
        assert result["status"] == "valid"
        assert result["valid"] is True

    def test_generate_agents_md_force(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Old")
        result = generate_agents_md(str(tmp_path), force=True)
        assert result["status"] == "overwritten"
        assert result["created"] is True
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Old" not in content
        assert "## Project Goals" in content

    def test_generate_agents_md_no_force(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Old")
        result = generate_agents_md(str(tmp_path), force=False)
        assert result["status"] == "exists"
        assert result["created"] is False

    def test_scan_for_missing_agents_md(self, tmp_path: Path) -> None:
        # Create a subproject with a marker
        subproject = tmp_path / "subproject"
        subproject.mkdir()
        (subproject / "package.json").write_text("{}")
        # No AGENTS.md

        results = scan_for_missing_agents_md(str(tmp_path), max_depth=2)
        assert len(results) >= 1
        assert any(r["name"] == "subproject" and r["status"] == "missing" for r in results)

    def test_scan_finds_existing(self, tmp_path: Path) -> None:
        subproject = tmp_path / "subproject"
        subproject.mkdir()
        (subproject / "package.json").write_text("{}")
        (subproject / "AGENTS.md").write_text("# OK")

        results = scan_for_missing_agents_md(str(tmp_path), max_depth=2)
        assert any(r["name"] == "subproject" and r["status"] == "ok" for r in results)
