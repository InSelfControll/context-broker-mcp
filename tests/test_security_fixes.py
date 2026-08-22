"""Regression tests for the CB-001..CB-014 review fixes."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from context_broker.context_ttc.tools.id_tools import safe_id
from context_broker.security_ttc.tools import _scan_content_for_secrets
from context_broker.storage_ttc.tasks.json_tasks import load_json_data, save_json_data
from context_broker.storage_ttc.tools.path_tools import (
    get_storage_dirs,
    sanitize_storage_component,
)


# ---------------------------------------------------------------------------
# CB-002 — storage path escape
# ---------------------------------------------------------------------------

class TestStorageContainment:
    @pytest.mark.parametrize("bad", ["../x", "a/../../b", "/abs/path", "C:/win", ".."])
    def test_component_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            sanitize_storage_component(bad, kind="project_name", allow_nested=True)

    def test_project_name_must_be_single_component(self) -> None:
        with pytest.raises(ValueError):
            sanitize_storage_component("a/b", kind="project_name")

    def test_nested_subdir_allowed(self) -> None:
        assert sanitize_storage_component("a/b/c", kind="subdir", allow_nested=True) == "a/b/c"

    def test_get_storage_dirs_rejects_escape(self) -> None:
        with pytest.raises(ValueError):
            get_storage_dirs("../evil")

    def test_save_rejects_traversal_filename(self) -> None:
        with pytest.raises(ValueError):
            save_json_data("proj", "../../etc/evil.json", {"x": 1})

    def test_load_rejects_secret_filename(self) -> None:
        with pytest.raises(ValueError):
            load_json_data("proj", ".env")


# ---------------------------------------------------------------------------
# CB-003 — full-slice, case-insensitive, assignment-shaped secret scanning
# ---------------------------------------------------------------------------

class TestSecretScanning:
    def test_secret_after_line_100_blocked(self) -> None:
        content = ("# padding\n" * 200) + "API_KEY=abc123\n"
        matched, _ = _scan_content_for_secrets(content)
        assert matched is True

    def test_lowercase_key_blocked(self) -> None:
        matched, _ = _scan_content_for_secrets("api_key=abc123\n")
        assert matched is True

    def test_yaml_style_blocked(self) -> None:
        matched, _ = _scan_content_for_secrets("  secret_key: abc123\n")
        assert matched is True

    def test_prose_allowed(self) -> None:
        matched, _ = _scan_content_for_secrets(
            "To reset your password, open settings.\n"
            "This document describes the secret sauce recipe.\n"
        )
        assert matched is False

    def test_code_assignment_allowed(self) -> None:
        matched, _ = _scan_content_for_secrets(
            "def authenticate(user, session_id):\n"
            "    token = create_token(session_id)\n"
            "    return token\n"
        )
        assert matched is False


# ---------------------------------------------------------------------------
# CB-004 — collision-free identifier normalization
# ---------------------------------------------------------------------------

class TestSafeId:
    def test_lossy_ids_do_not_collide(self) -> None:
        assert safe_id("a b") != safe_id("a-b")
        assert safe_id("a/b") != safe_id("a_b")
        assert safe_id("a b") != safe_id("a/b")

    def test_clean_ids_unchanged(self) -> None:
        assert safe_id("session-1_ok.v2") == "session-1_ok.v2"

    def test_default_applied(self) -> None:
        assert safe_id("") == "default"
        assert safe_id("", "user") == "user"

    def test_digest_deterministic(self) -> None:
        assert safe_id("a b") == safe_id("a b")


# ---------------------------------------------------------------------------
# CB-006 — regex DoS guard
# ---------------------------------------------------------------------------

class TestRegexSafety:
    def test_oversized_pattern_rejected(self, tmp_path: Path) -> None:
        from context_broker.indexer_ttc.tasks.literal_search_tasks import literal_search

        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="too long"):
            literal_search("a" * 5000, str(tmp_path), use_regex=True)

    def test_pathological_pattern_times_out(self, tmp_path: Path, monkeypatch) -> None:
        import time

        from context_broker.indexer_ttc.tasks import literal_search_tasks

        monkeypatch.setattr(literal_search_tasks, "REGEX_MATCH_TIMEOUT_SECONDS", 0.5)
        monkeypatch.setattr(
            literal_search_tasks,
            "_collect_files",
            lambda root: [str(tmp_path / "big.txt")],
        )
        # Non-matching input is what triggers catastrophic backtracking.
        (tmp_path / "big.txt").write_text("a" * 30_000 + "b", encoding="utf-8")

        start = time.monotonic()
        result = literal_search_tasks.literal_search(
            "(a+)+$", str(tmp_path), use_regex=True
        )
        elapsed = time.monotonic() - start
        assert elapsed < 10  # would hang for minutes without the timeout
        assert result["total_matches"] == 0


# ---------------------------------------------------------------------------
# CB-007 — chat ledger concurrent appends
# ---------------------------------------------------------------------------

class TestChatLedgerRace:
    def test_concurrent_appends_keep_all_messages(self, tmp_path: Path, monkeypatch) -> None:
        from context_broker.context_ttc.tasks import chat_ledger

        monkeypatch.setattr(chat_ledger, "STORAGE_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(chat_ledger, "STORAGE_MODE", "global")

        def worker(n: int) -> None:
            for i in range(10):
                chat_ledger.append_turn(
                    str(tmp_path), "s1", [{"peer_id": "u", "content": f"m{n}-{i}"}]
                )

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        payload = chat_ledger.read_ledger(str(tmp_path), "s1")
        assert payload is not None
        assert len(payload["messages"]) == 40
        # No stray temp files left behind
        assert list((tmp_path / "chats").rglob("*.tmp")) == []


# ---------------------------------------------------------------------------
# CB-009 — chat cache circuit breaker retries instead of latching
# ---------------------------------------------------------------------------

class TestChatCacheBreaker:
    def test_failure_backs_off_then_recovers(self, monkeypatch) -> None:
        from context_broker.context_ttc.tasks import chat_cache

        monkeypatch.setattr(chat_cache, "REDIS_URL", "redis://fake")
        monkeypatch.setattr(chat_cache, "CHAT_CACHE_TTL_SECONDS", 60)
        chat_cache.reset_client_for_tests(None)

        clock = {"now": 1000.0}
        monkeypatch.setattr(chat_cache.time, "monotonic", lambda: clock["now"])

        class _BoomRedis:
            @staticmethod
            def from_url(*args, **kwargs):
                raise ConnectionError("redis down")

        import sys

        monkeypatch.setitem(sys.modules, "redis", _BoomRedis)
        assert chat_cache._get_client() is None
        assert chat_cache._REDIS_RETRY_AFTER > clock["now"]
        # Still in backoff: no retry
        assert chat_cache._get_client() is None
        # After the backoff window the next call retries (and fails again)
        clock["now"] += chat_cache._REDIS_RETRY_BACKOFF_SECONDS + 1
        assert chat_cache._get_client() is None
        assert chat_cache._REDIS_RETRY_AFTER > clock["now"]
        chat_cache.reset_client_for_tests(None)


# ---------------------------------------------------------------------------
# CB-011 — bounded router plan cache
# ---------------------------------------------------------------------------

class TestRouterPlanCacheBound:
    def test_cache_evicts_oldest(self, monkeypatch) -> None:
        from context_broker.router_ttc.tasks import router_tasks
        from context_broker.router_ttc.tools.registry_tools import (
            ToolDescriptor,
            ToolRegistry,
        )

        registry = ToolRegistry()
        registry.register(
            ToolDescriptor(
                id="t1",
                name="t1",
                category="test",
                description="semantic code search",
                schema_summary="{}",
                tags=["search"],
                permissions=[],
                risk_level="low",
                file_capable=False,
                network_capable=False,
                shell_capable=False,
            )
        )
        monkeypatch.setattr(router_tasks, "ROUTER_PLAN_CACHE_MAX", 3)
        router_tasks._PLAN_CACHE.clear()
        for i in range(10):
            router_tasks.route_task(
                f"find thing {i}", registry=registry, mode="plan_only", token_budget=100
            )
        assert len(router_tasks._PLAN_CACHE) <= 3
        router_tasks._PLAN_CACHE.clear()


# ---------------------------------------------------------------------------
# CB-012 — token-history dedupe happens before writing run files
# ---------------------------------------------------------------------------

class TestTokenReportDedupe:
    def test_identical_report_written_once(self, tmp_path: Path, monkeypatch) -> None:
        from context_broker.indexer_ttc.tools import state, token_report_tools

        calls = {"run": 0, "report": 0}
        monkeypatch.setattr(
            token_report_tools,
            "save_token_counter_run",
            lambda *a, **k: calls.__setitem__("run", calls["run"] + 1),
        )
        monkeypatch.setattr(
            token_report_tools,
            "save_token_counter_report",
            lambda *a, **k: calls.__setitem__("report", calls["report"] + 1),
        )
        state.LAST_TOKEN_REPORTS.clear()
        state.LAST_PERSISTED_TOKEN_REPORT_HASHES.clear()

        report = {"query": "q", "total_tokens": 10, "context_tokens": 5}
        token_report_tools.persist_token_report(str(tmp_path), report)
        token_report_tools.persist_token_report(str(tmp_path), dict(report))
        assert calls == {"run": 1, "report": 1}


# ---------------------------------------------------------------------------
# CB-013 — malformed numeric env vars cannot crash config import
# ---------------------------------------------------------------------------

class TestConfigParsing:
    def test_malformed_port_falls_back(self, monkeypatch) -> None:
        import importlib

        import context_broker.config as config

        monkeypatch.setenv("CONTEXT_BROKER_PORT", "not-a-number")
        monkeypatch.setenv("CONTEXT_BROKER_DASHBOARD_PORT", "")
        try:
            importlib.reload(config)
            assert config.PORT == 8765
            assert config.DASHBOARD_PORT == 8770
        finally:
            monkeypatch.undo()
            importlib.reload(config)


# ---------------------------------------------------------------------------
# CB-001 — bind gate + token auth
# ---------------------------------------------------------------------------

class TestBindGate:
    def test_non_loopback_without_token_refused(self, monkeypatch) -> None:
        from context_broker.server_ttc.tools import auth_tools

        monkeypatch.setattr(auth_tools, "AUTH_TOKEN", "")
        monkeypatch.setattr(auth_tools, "ALLOW_UNAUTHENTICATED_BIND", False)
        with pytest.raises(SystemExit):
            auth_tools.assert_bind_allowed("0.0.0.0", 8765, "MCP sse transport")

    def test_non_loopback_with_token_allowed(self, monkeypatch) -> None:
        from context_broker.server_ttc.tools import auth_tools

        monkeypatch.setattr(auth_tools, "AUTH_TOKEN", "s3cret")
        monkeypatch.setattr(auth_tools, "ALLOW_UNAUTHENTICATED_BIND", False)
        auth_tools.assert_bind_allowed("0.0.0.0", 8765, "MCP sse transport")

    def test_loopback_always_allowed(self, monkeypatch) -> None:
        from context_broker.server_ttc.tools import auth_tools

        monkeypatch.setattr(auth_tools, "AUTH_TOKEN", "")
        monkeypatch.setattr(auth_tools, "ALLOW_UNAUTHENTICATED_BIND", False)
        auth_tools.assert_bind_allowed("127.0.0.1", 8765, "MCP sse transport")

    def test_token_validation(self, monkeypatch) -> None:
        from context_broker.server_ttc.tools import auth_tools

        monkeypatch.setattr(auth_tools, "AUTH_TOKEN", "s3cret")
        assert auth_tools.token_valid("s3cret") is True
        assert auth_tools.token_valid("wrong") is False
        assert auth_tools.token_from({"authorization": "Bearer s3cret"}) == "s3cret"
        assert auth_tools.token_from({}, "query-tok") == "query-tok"


# ---------------------------------------------------------------------------
# CB-014 — downstream env allowlist (regression for the already-fixed finding)
# ---------------------------------------------------------------------------

class TestDownstreamEnvAllowlist:
    def test_unknown_xdg_var_not_inherited(self, monkeypatch) -> None:
        from context_broker.client_ttc.tools.environment_tools import filtered_stdio_env

        monkeypatch.setenv("XDG_SECRET_TOKEN", "leak-me-not")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leak-me-not")
        env = filtered_stdio_env()
        assert "XDG_SECRET_TOKEN" not in env
        assert "AWS_SECRET_ACCESS_KEY" not in env

    def test_explicit_extra_env_wins(self, monkeypatch) -> None:
        from context_broker.client_ttc.tools.environment_tools import filtered_stdio_env

        env = filtered_stdio_env({"CUSTOM_FLAG": "1"})
        assert env["CUSTOM_FLAG"] == "1"
