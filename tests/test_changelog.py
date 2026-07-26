"""Tests for changelog management module."""

from pathlib import Path


from context_broker.changelog_ttc.tools.changelog_tools import (
    COMMIT_TYPE_EMOJI,
    COMMIT_TYPE_LABEL,
    ParsedCommit,
    _parse_commit_message,
    categorize_commits,
    find_latest_changelog_version,
    format_changelog_entry,
    generate_changelog_section,
    get_changelog_summary,
    update_changelog,
    validate_changelog,
    _default_changelog_header,
)


class TestParseCommitMessage:
    """Tests for commit message parsing."""

    def test_simple_feat(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("feat: add new feature")
        assert commit_type == "feat"
        assert scope == ""
        assert is_breaking is False

    def test_feat_with_scope(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("feat(auth): add login")
        assert commit_type == "feat"
        assert scope == "auth"
        assert is_breaking is False

    def test_breaking_change(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("feat(api)!: remove old endpoint")
        assert commit_type == "feat"
        assert scope == "api"
        assert is_breaking is True

    def test_fix_commit(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("fix: resolve bug")
        assert commit_type == "fix"
        assert is_breaking is False

    def test_security_commit(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("security: patch vulnerability")
        assert commit_type == "security"
        assert is_breaking is False

    def test_non_conventional(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("some random commit")
        assert commit_type == ""
        assert scope == ""
        assert is_breaking is False

    def test_breaking_in_body(self) -> None:
        commit_type, scope, is_breaking = _parse_commit_message("chore: update deps with BREAKING CHANGE")
        assert is_breaking is True


class TestFormatChangelogEntry:
    """Tests for changelog entry formatting."""

    def test_basic_entry(self) -> None:
        commit = ParsedCommit(
            hash="abc123",
            short_hash="abc1234",
            subject="feat: add user auth",
            body="",
            author="Test User",
            date="2024-01-01",
            commit_type="feat",
            scope="",
            is_breaking=False,
            is_merge=False,
        )
        entry = format_changelog_entry(commit)
        assert "✨" in entry
        assert "add user auth" in entry
        assert "`abc1234`" in entry
        assert "[BREAKING]" not in entry

    def test_breaking_entry(self) -> None:
        commit = ParsedCommit(
            hash="abc123",
            short_hash="abc1234",
            subject="feat!: remove old API",
            body="",
            author="Test User",
            date="2024-01-01",
            commit_type="feat",
            scope="",
            is_breaking=True,
            is_merge=False,
        )
        entry = format_changelog_entry(commit)
        assert "[BREAKING]" in entry

    def test_pr_reference(self) -> None:
        commit = ParsedCommit(
            hash="abc123",
            short_hash="abc1234",
            subject="feat: add feature (#42)",
            body="",
            author="Test User",
            date="2024-01-01",
            commit_type="feat",
            scope="",
            is_breaking=False,
            is_merge=False,
            pr_number="42",
        )
        entry = format_changelog_entry(commit)
        assert "#42" in entry


class TestCategorizeCommits:
    """Tests for commit categorization."""

    def test_categorizes_correctly(self) -> None:
        commits = [
            ParsedCommit("a", "a", "feat: new thing", "", "", "", "feat", "", False, False),
            ParsedCommit("b", "b", "fix: bug fix", "", "", "", "fix", "", False, False),
            ParsedCommit("c", "c", "security: patch", "", "", "", "security", "", False, False),
            ParsedCommit("d", "d", "docs: readme", "", "", "", "docs", "", False, False),
        ]
        categories = categorize_commits(commits)
        assert "Added" in categories
        assert "Fixed" in categories
        assert "Security" in categories
        assert "Documentation" in categories
        assert len(categories["Added"]) == 1
        assert len(categories["Fixed"]) == 1

    def test_skips_plain_merge_commits(self) -> None:
        commits = [
            ParsedCommit("a", "a", "Merge branch 'main'", "", "", "", "", "", False, True),
            ParsedCommit("b", "b", "feat: new thing", "", "", "", "feat", "", False, False),
        ]
        categories = categorize_commits(commits)
        assert "Added" in categories
        assert len(categories["Added"]) == 1

    def test_keeps_merge_with_pr(self) -> None:
        commits = [
            ParsedCommit(
                "a", "a", "Merge pull request #1", "", "", "", "", "", False, True, "1"
            ),
        ]
        categories = categorize_commits(commits)
        assert len(categories) == 1


class TestGenerateChangelogSection:
    """Tests for changelog section generation."""

    def test_generates_sections(self) -> None:
        commits = [
            ParsedCommit("a", "a", "feat: add auth", "", "", "", "feat", "", False, False),
            ParsedCommit("b", "b", "fix: fix bug", "", "", "", "fix", "", False, False),
        ]
        section = generate_changelog_section("0.2.0", commits, date="2024-01-15")
        assert "## [0.2.0] — 2024-01-15" in section
        assert "### Added" in section
        assert "### Fixed" in section
        assert "✨" in section
        assert "🐛" in section

    def test_empty_commits(self) -> None:
        section = generate_changelog_section("0.1.0", [], date="2024-01-15")
        assert "## [0.1.0] — 2024-01-15" in section


class TestChangelogFileOperations:
    """Tests for file-based changelog operations."""

    def test_default_header(self) -> None:
        header = _default_changelog_header()
        assert "# Changelog" in header
        assert "Keep a Changelog" in header

    def test_find_version_in_existing(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [0.1.0] — 2024-01-01\n\n### Added\n- feat: initial\n")
        version, since = find_latest_changelog_version(changelog)
        assert version == "0.1.0"

    def test_find_version_missing(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        version, since = find_latest_changelog_version(changelog)
        assert version == ""
        assert since == ""

    def test_get_summary_missing(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        result = get_changelog_summary(changelog)
        assert result["status"] == "missing"

    def test_get_summary_existing(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [0.2.0] — 2024-02-01\n\n### Added\n- feat: new\n\n"
            "## [0.1.0] — 2024-01-01\n\n### Added\n- feat: init\n"
        )
        result = get_changelog_summary(changelog)
        assert result["status"] == "exists"
        assert result["versions"] == "2"
        assert result["latest_version"] == "0.2.0"
        assert result["total_entries"] == "2"


class TestUpdateChangelog:
    """Tests for update_changelog."""

    def test_creates_new_changelog(self, tmp_path: Path) -> None:
        # Need a git repo to test this properly
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        # Create a file and commit
        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: initial commit"], cwd=repo, check=True, capture_output=True)

        changelog = repo / "CHANGELOG.md"
        result = update_changelog(changelog, version="Unreleased", cwd=str(repo))
        assert result["status"] == "updated"
        assert "1" in result["commit_count"]
        assert changelog.exists()
        content = changelog.read_text()
        assert "## [Unreleased]" in content
        assert "initial commit" in content

    def test_no_changes(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_default_changelog_header())
        # No git repo = no commits
        result = update_changelog(changelog, version="Unreleased", cwd=str(tmp_path))
        assert result["status"] == "no_changes"


class TestValidateChangelog:
    """Tests for validate_changelog."""

    def test_missing_changelog(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        result = validate_changelog(changelog)
        assert result["status"] == "missing"
        assert result["valid"] is False

    def test_up_to_date(self, tmp_path: Path) -> None:
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: initial"], cwd=repo, check=True, capture_output=True)

        changelog = repo / "CHANGELOG.md"
        update_changelog(changelog, version="0.1.0", cwd=str(repo))

        result = validate_changelog(changelog)
        assert result["status"] == "up_to_date"
        assert result["valid"] is True

    def test_changelog_only_commit_does_not_require_recursive_entry(
        self,
        tmp_path: Path,
    ) -> None:
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "app.py").write_text("VALUE = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        changelog = repo / "CHANGELOG.md"
        update_changelog(changelog, version="0.1.0", cwd=str(repo))
        subprocess.run(
            ["git", "add", "CHANGELOG.md"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "docs: update changelog"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = validate_changelog(changelog)

        assert result["status"] == "up_to_date"
        assert result["valid"] is True
        assert result["missing_count"] == 0

    def test_mixed_changelog_and_code_commit_still_requires_entry(
        self,
        tmp_path: Path,
    ) -> None:
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "app.py").write_text("VALUE = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        changelog = repo / "CHANGELOG.md"
        update_changelog(changelog, version="0.1.0", cwd=str(repo))
        subprocess.run(
            ["git", "add", "CHANGELOG.md"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "docs: establish changelog"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "app.py").write_text("VALUE = 2\n")
        changelog.write_text(changelog.read_text() + "\nmanual note\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "fix: change code and changelog"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = validate_changelog(changelog)

        assert result["status"] == "outdated"
        assert result["valid"] is False
        assert result["missing_count"] == 1


class TestEmojiAndLabels:
    """Tests for emoji and label mappings."""

    def test_all_types_have_emoji(self) -> None:
        for commit_type in COMMIT_TYPE_LABEL:
            assert commit_type in COMMIT_TYPE_EMOJI, f"Missing emoji for {commit_type}"

    def test_all_types_have_label(self) -> None:
        for commit_type in COMMIT_TYPE_EMOJI:
            assert commit_type in COMMIT_TYPE_LABEL, f"Missing label for {commit_type}"

    def test_common_types(self) -> None:
        assert COMMIT_TYPE_EMOJI["feat"] == "✨"
        assert COMMIT_TYPE_EMOJI["fix"] == "🐛"
        assert COMMIT_TYPE_EMOJI["security"] == "🔒"
        assert COMMIT_TYPE_LABEL["feat"] == "Added"
        assert COMMIT_TYPE_LABEL["fix"] == "Fixed"
        assert COMMIT_TYPE_LABEL["security"] == "Security"
