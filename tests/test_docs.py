"""Tests for feature documentation generation."""

from pathlib import Path

import pytest

from context_broker.docs_ttc.tools.docs_tools import (
    _determine_doc_filename,
    _generate_doc_content,
    _get_changed_files,
    _has_existing_feature_docs,
    _infer_feature_from_files,
    _infer_feature_from_scope,
    ensure_feature_docs,
    get_docs_summary,
    scan_for_missing_docs,
)


class TestFeatureInference:
    """Tests for feature name inference."""

    def test_scope_agents(self) -> None:
        assert _infer_feature_from_scope("agents") == "agents"

    def test_scope_security(self) -> None:
        assert _infer_feature_from_scope("security") == "security"

    def test_scope_with_ttc(self) -> None:
        assert _infer_feature_from_scope("agents_ttc") == "agents"

    def test_files_agents(self) -> None:
        files = ["context_broker/agents_ttc/tools.py", "context_broker/agents.py"]
        assert _infer_feature_from_files(files) == "agents"

    def test_files_security(self) -> None:
        files = ["context_broker/security_ttc/tools.py"]
        assert _infer_feature_from_files(files) == "security"

    def test_files_general(self) -> None:
        files = ["README.md"]
        assert _infer_feature_from_files(files) == "readme"

    def test_files_unknown(self) -> None:
        files = ["random.txt"]
        assert _infer_feature_from_files(files) == "general"


class TestDocFilename:
    """Tests for doc filename determination."""

    def test_first_doc_no_existing(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        path = _determine_doc_filename(docs_dir, "agents", "feat")
        assert path.name == "feat.md"
        assert path.parent.name == "agents"

    def test_second_doc_with_existing(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        # Create existing doc
        (docs_dir / "agents").mkdir(parents=True)
        (docs_dir / "agents" / "feat.md").write_text("existing")

        path = _determine_doc_filename(docs_dir, "agents", "fix")
        assert path.name == "agents-fix.md"

    def test_creates_directory(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        path = _determine_doc_filename(docs_dir, "security", "feat")
        assert path.parent.exists()


class TestExistingDocsCheck:
    """Tests for checking existing feature docs."""

    def test_no_docs(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        assert _has_existing_feature_docs(docs_dir, "agents") is False

    def test_has_docs(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        (docs_dir / "agents").mkdir(parents=True)
        (docs_dir / "agents" / "feat.md").write_text("x")
        assert _has_existing_feature_docs(docs_dir, "agents") is True

    def test_empty_dir(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        (docs_dir / "agents").mkdir(parents=True)
        assert _has_existing_feature_docs(docs_dir, "agents") is False


class TestDocContentGeneration:
    """Tests for doc content generation."""

    def test_generates_content(self) -> None:
        commits = [
            {
                "hash": "abc1234",
                "subject": "add auth system",
                "full_subject": "feat: add auth system",
                "body": "Details about auth",
                "type": "feat",
                "scope": "auth",
                "feature": "auth",
                "is_breaking": False,
                "files": ["auth.py", "models.py"],
            }
        ]
        content = _generate_doc_content("auth", "feat", commits)
        assert "# ✨ Auth — Added" in content
        assert "add auth system" in content
        assert "abc1234" in content
        assert "auth.py" in content

    def test_breaking_changes_section(self) -> None:
        commits = [
            {
                "hash": "abc1234",
                "subject": "remove old API",
                "full_subject": "feat!: remove old API",
                "body": "",
                "type": "feat",
                "scope": "api",
                "feature": "api",
                "is_breaking": True,
                "files": ["api.py"],
            }
        ]
        content = _generate_doc_content("api", "feat", commits)
        assert "⚠️ Breaking Changes" in content
        assert "remove old API" in content

    def test_related_files_limit(self) -> None:
        commits = [
            {
                "hash": "abc1234",
                "subject": "big refactor",
                "full_subject": "refactor: big refactor",
                "body": "",
                "type": "refactor",
                "scope": "",
                "feature": "core",
                "is_breaking": False,
                "files": [f"file{i}.py" for i in range(25)],
            }
        ]
        content = _generate_doc_content("core", "refactor", commits)
        assert "and 5 more files" in content


class TestEnsureFeatureDocs:
    """Tests for ensure_feature_docs."""

    def test_creates_docs(self, tmp_path: Path) -> None:
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        (repo / "agents.py").write_text("# agents")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(agents): add agent system"], cwd=repo, check=True, capture_output=True)

        result = ensure_feature_docs(str(repo))
        assert result["status"] == "updated"
        assert result["created_count"] >= 1

        # Check file was created
        docs_dir = repo / "docs"
        assert docs_dir.exists()
        assert any(docs_dir.rglob("*.md"))

    def test_skips_existing(self, tmp_path: Path) -> None:
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        (repo / "agents.py").write_text("# agents")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(agents): add agent system"], cwd=repo, check=True, capture_output=True)

        # First run creates docs
        ensure_feature_docs(str(repo))
        # Second run should find existing
        result = ensure_feature_docs(str(repo))
        assert result["existing_count"] >= 1

    def test_no_commits(self, tmp_path: Path) -> None:
        result = ensure_feature_docs(str(tmp_path))
        assert result["status"] == "no_changes"


class TestScanForMissingDocs:
    """Tests for scan_for_missing_docs."""

    def test_finds_missing(self, tmp_path: Path) -> None:
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        (repo / "agents.py").write_text("# agents")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(agents): add agent system"], cwd=repo, check=True, capture_output=True)

        result = scan_for_missing_docs(str(repo))
        assert result["status"] == "missing"
        assert result["missing_count"] >= 1

    def test_complete_when_docs_exist(self, tmp_path: Path) -> None:
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        (repo / "agents.py").write_text("# agents")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(agents): add agent system"], cwd=repo, check=True, capture_output=True)

        ensure_feature_docs(str(repo))
        result = scan_for_missing_docs(str(repo))
        assert result["status"] == "complete"


class TestDocsSummary:
    """Tests for docs summary."""

    def test_missing_docs(self, tmp_path: Path) -> None:
        result = get_docs_summary(str(tmp_path))
        assert result["status"] == "missing"

    def test_existing_docs(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        (docs_dir / "agents").mkdir(parents=True)
        (docs_dir / "agents" / "feat.md").write_text("x")
        (docs_dir / "security").mkdir(parents=True)
        (docs_dir / "security" / "feat.md").write_text("y")

        result = get_docs_summary(str(tmp_path))
        assert result["status"] == "exists"
        assert result["features"] == 2
        assert result["total_docs"] == 2
        assert "agents" in result["features_list"]
        assert "security" in result["features_list"]
