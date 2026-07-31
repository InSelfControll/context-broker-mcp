"""Tests for secret-file security protection."""

from pathlib import Path


from context_broker.config import SECRET_ENV_KEY_PATTERNS, SECRET_FILE_PATTERNS
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.project_ttc.tasks.ignore_tasks import should_ignore
from context_broker.security_ttc.tools import (
    audit_log_secret_block,
    get_security_summary,
    is_secret_file,
    _match_secret_pattern,
    _scan_content_for_secrets,
)


class TestSecretPatternMatching:
    """Tests for filename/path secret pattern matching."""

    def test_dotenv_blocked(self) -> None:
        matched, pattern = _match_secret_pattern(".env")
        assert matched is True
        assert pattern in {".env", "*.env"}

    def test_dotenv_local_blocked(self) -> None:
        matched, pattern = _match_secret_pattern(".env.local")
        assert matched is True

    def test_dotenv_production_blocked(self) -> None:
        matched, pattern = _match_secret_pattern(".env.production")
        assert matched is True

    def test_aws_credentials_blocked(self) -> None:
        matched, _ = _match_secret_pattern(".aws/credentials")
        assert matched is True

    def test_id_rsa_blocked(self) -> None:
        matched, _ = _match_secret_pattern("id_rsa")
        assert matched is True

    def test_pem_blocked(self) -> None:
        matched, _ = _match_secret_pattern("cert.pem")
        assert matched is True

    def test_tfstate_blocked(self) -> None:
        matched, _ = _match_secret_pattern("terraform.tfstate")
        assert matched is True

    def test_secrets_json_blocked(self) -> None:
        matched, _ = _match_secret_pattern("secrets.json")
        assert matched is True

    def test_normal_file_allowed(self) -> None:
        matched, _ = _match_secret_pattern("main.py")
        assert matched is False

    def test_normal_config_allowed(self) -> None:
        matched, _ = _match_secret_pattern("pyproject.toml")
        assert matched is False

    def test_readme_allowed(self) -> None:
        matched, _ = _match_secret_pattern("README.md")
        assert matched is False

    def test_env_in_pathname_allowed(self) -> None:
        matched, _ = _match_secret_pattern("environment.py")
        assert matched is False

    def test_npmrc_not_blocked_by_filename(self) -> None:
        """.npmrc should NOT be in SECRET_FILE_PATTERNS (content-based only)."""
        matched, _ = _match_secret_pattern(".npmrc")
        assert matched is False
        assert ".npmrc" not in SECRET_FILE_PATTERNS

    def test_yarnrc_not_blocked_by_filename(self) -> None:
        """.yarnrc should NOT be in SECRET_FILE_PATTERNS (content-based only)."""
        matched, _ = _match_secret_pattern(".yarnrc")
        assert matched is False
        assert ".yarnrc" not in SECRET_FILE_PATTERNS


class TestContentSecretScanning:
    """Tests for content-based secret signature detection."""

    def test_api_key_content_blocked(self) -> None:
        content = "API_KEY=sk-abc123def456\nDATABASE_URL=postgres://localhost"
        matched, sig = _scan_content_for_secrets(content)
        assert matched is True
        assert "API_KEY" in sig

    def test_password_content_blocked(self) -> None:
        content = "# config\nPASSWORD=supersecret123\n"
        matched, sig = _scan_content_for_secrets(content)
        assert matched is True
        assert "PASSWORD" in sig

    def test_secret_key_content_blocked(self) -> None:
        content = "SECRET_KEY=django-insecure-abc123\n"
        matched, sig = _scan_content_for_secrets(content)
        assert matched is True
        assert "SECRET_KEY" in sig

    def test_normal_code_allowed(self) -> None:
        content = "def hello_world():\n    print('Hello')\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is False

    def test_env_file_variants(self) -> None:
        content = "TOKEN=Bearer abc123\n"
        matched, sig = _scan_content_for_secrets(content)
        assert matched is True
        assert "Bearer " in sig

    def test_comment_with_secret_word_allowed(self) -> None:
        content = "# This is a secret algorithm\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is False

    def test_aws_access_key_blocked(self) -> None:
        content = "ACCESS_KEY=AKIAIOSFODNN7EXAMPLE\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is True

    def test_npmrc_with_auth_token_blocked(self) -> None:
        """.npmrc containing authToken should be blocked by content scanning."""
        content = "//registry.npmjs.org/:_authToken=npm_xxxxx\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is True

    def test_npmrc_without_auth_allowed(self) -> None:
        """.npmrc with only registry config should pass content scanning."""
        content = "registry=https://registry.npmjs.org/\nsave-exact=true\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is False


class TestIsSecretFile:
    """Tests for the combined is_secret_file function."""

    def test_filename_match(self) -> None:
        is_secret, reason = is_secret_file("/project/.env", ".env")
        assert is_secret is True
        assert "blocked by secret pattern" in reason

    def test_content_match(self) -> None:
        content = "API_KEY=secret123\n"
        is_secret, reason = is_secret_file("/project/config.txt", "config.txt", content=content)
        assert is_secret is True
        assert "blocked by content signature" in reason

    def test_no_match(self) -> None:
        is_secret, reason = is_secret_file("/project/main.py", "main.py")
        assert is_secret is False
        assert reason == ""

    def test_no_content_no_match(self) -> None:
        is_secret, _ = is_secret_file("/project/my_secrets.py", "my_secrets.py")
        assert is_secret is False

    def test_npmrc_no_auth_not_secret(self) -> None:
        """.npmrc without auth should not be flagged as secret."""
        is_secret, _ = is_secret_file("/project/.npmrc", ".npmrc")
        assert is_secret is False


class TestShouldIgnoreSecurity:
    """Tests that should_ignore blocks secret files."""

    def test_should_ignore_blocks_env_file(self) -> None:
        result = should_ignore("/project/.env", ".env", [], set())
        assert result is True

    def test_should_ignore_blocks_aws_credentials(self) -> None:
        result = should_ignore("/project/.aws/credentials", ".aws/credentials", [], set())
        assert result is True

    def test_should_ignore_allows_normal_files(self) -> None:
        result = should_ignore("/project/main.py", "main.py", [], set())
        assert result is False

    def test_should_ignore_respects_gitignore(self) -> None:
        result = should_ignore("/project/__pycache__/foo.pyc", "__pycache__/foo.pyc", ["__pycache__/*"], set())
        assert result is True

    def test_should_ignore_allows_npmrc(self) -> None:
        """.npmrc without auth should pass through should_ignore."""
        result = should_ignore("/project/.npmrc", ".npmrc", [], set())
        assert result is False

    def test_should_ignore_blocks_iso_and_disk_images(self) -> None:
        assert should_ignore(
            "/project/ofir-nixos-kde-installer.iso",
            "ofir-nixos-kde-installer.iso",
            [],
            set(),
        )
        assert should_ignore("/project/Installer.ISO", "Installer.ISO", [], set())
        assert should_ignore("/project/disk.qcow2", "disk.qcow2", [], set())
        assert should_ignore("/project/root.img", "root.img", [], set())
        assert should_ignore("/project/bundle.tar.gz", "dist/bundle.tar.gz", [], set())


class TestReadFileContentSecurity:
    """Tests that read_file_content blocks secret files."""

    def test_blocks_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=secret123\n")
        result = read_file_content(str(env_file))
        assert result is None

    def test_blocks_renamed_env_file(self, tmp_path: Path) -> None:
        secret_file = tmp_path / "config.txt"
        secret_file.write_text("API_KEY=secret123\nSECRET_KEY=abc\n")
        result = read_file_content(str(secret_file))
        assert result is None

    def test_allows_normal_file(self, tmp_path: Path) -> None:
        normal_file = tmp_path / "main.py"
        normal_file.write_text("def hello():\n    print('world')\n")
        result = read_file_content(str(normal_file))
        assert result is not None
        assert "def hello" in result

    def test_allows_safe_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "settings.json"
        config_file.write_text('{"debug": true, "port": 8080}')
        result = read_file_content(str(config_file))
        assert result is not None

    def test_blocks_secrets_json(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text('{"api_key": "secret"}')
        result = read_file_content(str(secrets_file))
        assert result is None

    def test_allows_npmrc_without_auth(self, tmp_path: Path) -> None:
        """.npmrc with only registry config should be readable."""
        npmrc = tmp_path / ".npmrc"
        npmrc.write_text("registry=https://registry.npmjs.org/\nsave-exact=true\n")
        result = read_file_content(str(npmrc))
        assert result is not None
        assert "registry" in result

    def test_blocks_npmrc_with_auth(self, tmp_path: Path) -> None:
        """.npmrc with authToken should be blocked by content scanning."""
        npmrc = tmp_path / ".npmrc"
        npmrc.write_text("//registry.npmjs.org/:_authToken=npm_xxxxx\n")
        result = read_file_content(str(npmrc))
        assert result is None


class TestSecuritySummary:
    """Tests for security configuration summary."""

    def test_summary_structure(self) -> None:
        summary = get_security_summary()
        assert "secret_file_patterns" in summary
        assert "secret_content_signatures" in summary
        assert summary["secret_file_patterns"] > 0
        assert summary["secret_content_signatures"] > 0

    def test_patterns_not_empty(self) -> None:
        assert len(SECRET_FILE_PATTERNS) > 0
        assert len(SECRET_ENV_KEY_PATTERNS) > 0


class TestAuditLogging:
    """Tests for security audit logging."""

    def test_audit_log_does_not_raise(self) -> None:
        audit_log_secret_block(".env", "blocked by pattern '.env'", operation="index")
        audit_log_secret_block("config.txt", "blocked by signature 'API_KEY'", operation="read")
