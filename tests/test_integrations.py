"""Tests for optional cache, context, and dashboard integrations."""

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from context_broker import config
from context_broker.context_ttc.tasks import honcho_tasks, redis_tasks
from context_broker.dashboard_ttc.codebase.api import create_app
from context_broker.dashboard_ttc.tasks import data_tasks
from context_broker.indexer_ttc.tools import cache_tools, state


# ---------------------------------------------------------------------------
# Fake Redis (string/set/hash/list) — enough for the context backend's needs.
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = defaultdict(set)
        self.hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.strings: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def ping(self) -> bool:
        return True

    def sadd(self, key: str, *values: str) -> None:
        self.sets[key].update(values)

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def scard(self, key: str) -> int:
        return len(self.sets.get(key, ()))

    def hset(self, key: str, mapping: dict[str, str] | None = None, **kwargs) -> None:
        if mapping:
            self.hashes[key].update(mapping)
        if kwargs:
            self.hashes[key].update(kwargs)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def rpush(self, key: str, value: str) -> int:
        self.lists[key].append(value)
        return len(self.lists[key])

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        data = self.lists.get(key, [])
        if end == -1:
            return list(data[start:])
        return list(data[start : end + 1])

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def lindex(self, key: str, index: int) -> str | None:
        data = self.lists.get(key, [])
        if not data:
            return None
        try:
            return data[index]
        except IndexError:
            return None

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            for store in (self.strings, self.hashes, self.lists, self.sets, self.ttls):
                if key in store:
                    del store[key]
                    removed += 1
        return removed

    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        try:
            current = int(self.hashes[key].get(field, "0") or "0")
        except ValueError:
            current = 0
        current += amount
        self.hashes[key][field] = str(current)
        return current

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    """Buffered MULTI/EXEC double: records calls, applies them on execute()."""

    def __init__(self, client: "FakeRedis") -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def recorder(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return recorder

    def execute(self) -> list:
        results = []
        for name, args, kwargs in self._ops:
            results.append(getattr(self._client, name)(*args, **kwargs))
        self._ops.clear()
        return results


# ---------------------------------------------------------------------------
# Cache + Honcho status sanity checks (kept from earlier coverage)
# ---------------------------------------------------------------------------


def test_query_cache_persists_to_local_json(tmp_path: Path) -> None:
    state.QUERY_CACHE.clear()
    try:
        cache = cache_tools.load_query_cache(str(tmp_path))
        assert cache == {}

        state.QUERY_CACHE[str(tmp_path)] = {"abc": {"query": "demo"}}
        cache_tools.save_query_cache(str(tmp_path))

        cache_path = tmp_path / ".cache" / "context-broker.json"
        assert cache_path.exists()
    finally:
        state.QUERY_CACHE.clear()


def test_honcho_status_is_disabled_by_default() -> None:
    status = honcho_tasks.get_context_backend_status()
    assert status["backend"] in {"none", "honcho", "redis"}
    if status["backend"] == "none":
        assert status["enabled"] is False


def test_query_cache_index_fingerprint_invalidates_new_files() -> None:
    original_mtimes = {"/repo/a.py": 1.0}
    changed_mtimes = {"/repo/a.py": 1.0, "/repo/b.py": 1.0}
    cache_entry = {
        "index_fingerprint": cache_tools.generate_index_fingerprint(original_mtimes),
    }
    assert cache_tools.is_cache_valid(cache_entry, original_mtimes) is True
    assert cache_tools.is_cache_valid(cache_entry, changed_mtimes) is False


def test_honcho_session_id_is_project_scoped(tmp_path: Path) -> None:
    first = honcho_tasks._honcho_session_id("chat", str(tmp_path))
    second = honcho_tasks._honcho_session_id("chat", str(tmp_path / "other"))
    assert first != second
    assert first.startswith("context-broker-")
    assert first.endswith("-chat")


# ---------------------------------------------------------------------------
# Redis-backed cross-chat context backend
# ---------------------------------------------------------------------------


def _enable_redis_backend(monkey_attrs: dict[str, object]) -> FakeRedis:
    fake = FakeRedis()
    config.CONTEXT_BACKEND = "redis"
    config.REDIS_URL = "redis://fake"
    redis_tasks.CONTEXT_BACKEND = "redis"
    redis_tasks.REDIS_URL = "redis://fake"
    redis_tasks.reset_client_for_tests(fake)
    monkey_attrs["fake"] = fake
    return fake


def _restore_backend(original_backend: str, original_url: str) -> None:
    config.CONTEXT_BACKEND = original_backend
    config.REDIS_URL = original_url
    redis_tasks.CONTEXT_BACKEND = original_backend
    redis_tasks.REDIS_URL = original_url
    redis_tasks.reset_client_for_tests(None)


def test_redis_backend_save_and_load_roundtrip(tmp_path: Path) -> None:
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    state_holder: dict[str, object] = {}
    fake = _enable_redis_backend(state_holder)
    try:
        save = redis_tasks.save_redis_chat_context(
            session_id="chat-1",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi back",
        )
        assert save["backend"] == "redis"
        assert save["messages_saved"] == 2

        loaded = redis_tasks.load_redis_chat_context(
            session_id="chat-1", project_root=str(tmp_path)
        )
        assert loaded["message_count"] == 2
        assert [m["content"] for m in loaded["messages"]] == ["hello", "hi back"]

        projects = redis_tasks.list_projects()
        assert len(projects) == 1
        assert projects[0]["session_count"] == 1

        sessions = redis_tasks.list_sessions(projects[0]["digest"])
        assert sessions[0]["session_id"] == "chat-1"
        assert sessions[0]["message_count"] == 2

        # search_query filter
        filtered = redis_tasks.load_redis_chat_context(
            session_id="chat-1",
            project_root=str(tmp_path),
            search_query="hi back",
        )
        assert filtered["message_count"] == 1

        # Sanity-check the fake actually got hit
        assert fake.scard(f"{config.REDIS_KEY_PREFIX}:ctx:projects") == 1
    finally:
        _restore_backend(original_backend, original_url)


def test_dashboard_data_tasks_use_active_backend(tmp_path: Path) -> None:
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    # data_tasks reads CONTEXT_BACKEND at call time via module attr
    data_tasks.CONTEXT_BACKEND = "redis"
    try:
        redis_tasks.save_redis_chat_context(
            session_id="alpha",
            project_root=str(tmp_path),
            user_message="ping",
            assistant_message="pong",
        )
        projects = data_tasks.list_projects()
        assert projects and projects[0]["session_count"] == 1
        digest = projects[0]["digest"]
        sessions = data_tasks.list_sessions(digest)
        assert sessions[0]["session_id"] == "alpha"
        session = data_tasks.load_session(digest, "alpha")
        assert session["message_count"] == 2
    finally:
        data_tasks.CONTEXT_BACKEND = original_backend
        _restore_backend(original_backend, original_url)


def test_dashboard_data_tasks_reject_other_backends() -> None:
    original_backend = data_tasks.CONTEXT_BACKEND
    data_tasks.CONTEXT_BACKEND = "honcho"
    try:
        try:
            data_tasks.list_projects()
        except data_tasks.DashboardError as exc:
            assert "redis" in str(exc).lower()
        else:
            raise AssertionError("expected DashboardError")
    finally:
        data_tasks.CONTEXT_BACKEND = original_backend


# ---------------------------------------------------------------------------
# Dashboard HTTP surface
# ---------------------------------------------------------------------------


def test_dashboard_routes_render_projects_and_sessions(tmp_path: Path) -> None:
    from starlette.testclient import TestClient

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    data_tasks.CONTEXT_BACKEND = "redis"
    try:
        redis_tasks.save_redis_chat_context(
            session_id="alpha",
            project_root=str(tmp_path),
            user_message="ping",
            assistant_message="pong",
        )
        app = create_app()
        client = TestClient(app)

        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["backend"] == "redis"

        r = client.get("/api/projects")
        assert r.status_code == 200
        body = r.json()
        assert body["backend"] == "redis"
        digest = body["projects"][0]["digest"]

        r = client.get(f"/api/projects/{digest}/sessions")
        assert r.status_code == 200
        assert r.json()["sessions"][0]["session_id"] == "alpha"

        r = client.get(f"/api/projects/{digest}/sessions/alpha")
        assert r.status_code == 200
        assert r.json()["message_count"] == 2

        r = client.get("/")
        assert r.status_code == 200
        assert "Context Broker" in r.text
        assert "alpha" not in r.text  # session id appears only on project page
        assert digest in r.text

        r = client.get(f"/projects/{digest}")
        assert r.status_code == 200
        assert "alpha" in r.text

        r = client.get(f"/projects/{digest}/sessions/alpha")
        assert r.status_code == 200
        assert "ping" in r.text and "pong" in r.text
    finally:
        data_tasks.CONTEXT_BACKEND = original_backend
        _restore_backend(original_backend, original_url)


def test_dashboard_api_projects_errors_when_backend_unsupported() -> None:
    from starlette.testclient import TestClient

    original_backend = data_tasks.CONTEXT_BACKEND
    data_tasks.CONTEXT_BACKEND = "honcho"
    try:
        client = TestClient(create_app())
        r = client.get("/api/projects")
        assert r.status_code == 400
        assert "error" in r.json()
    finally:
        data_tasks.CONTEXT_BACKEND = original_backend


# ---------------------------------------------------------------------------
# Chat-payload cache
# ---------------------------------------------------------------------------


def _enable_chat_cache(client) -> None:
    from context_broker.context_ttc.tasks import chat_cache

    config.REDIS_URL = "redis://fake"
    chat_cache.REDIS_URL = "redis://fake"
    chat_cache.CHAT_CACHE_TTL_SECONDS = 60
    chat_cache.reset_client_for_tests(client)


def _disable_chat_cache(original_url: str, original_ttl: int) -> None:
    from context_broker.context_ttc.tasks import chat_cache

    config.REDIS_URL = original_url
    chat_cache.REDIS_URL = original_url
    chat_cache.CHAT_CACHE_TTL_SECONDS = original_ttl
    chat_cache.reset_client_for_tests(None)


def test_chat_cache_put_get_invalidate_roundtrip(tmp_path: Path) -> None:
    from context_broker.context_ttc.tasks import chat_cache

    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    fake = FakeRedis()
    _enable_chat_cache(fake)
    try:
        params = {"backend": "honcho", "tokens": 100, "search_query": ""}
        assert chat_cache.get(str(tmp_path), "s1", **params) is None

        payload = {"messages": [{"peer_id": "user", "content": "hi"}]}
        assert chat_cache.put(str(tmp_path), "s1", payload, **params) is True
        got = chat_cache.get(str(tmp_path), "s1", **params)
        assert got == payload

        # Different signature → cache miss
        assert chat_cache.get(str(tmp_path), "s1", backend="redis", tokens=100) is None

        removed = chat_cache.invalidate(str(tmp_path), "s1")
        assert removed == 1
        assert chat_cache.get(str(tmp_path), "s1", **params) is None
    finally:
        _disable_chat_cache(original_url, original_ttl)


def test_chat_cache_disabled_when_ttl_is_zero(tmp_path: Path) -> None:
    from context_broker.context_ttc.tasks import chat_cache

    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    fake = FakeRedis()
    config.REDIS_URL = "redis://fake"
    chat_cache.REDIS_URL = "redis://fake"
    chat_cache.CHAT_CACHE_TTL_SECONDS = 0
    chat_cache.reset_client_for_tests(fake)
    try:
        assert chat_cache.put(str(tmp_path), "s1", {"x": 1}, backend="honcho") is False
        assert chat_cache.get(str(tmp_path), "s1", backend="honcho") is None
    finally:
        _disable_chat_cache(original_url, original_ttl)


def test_dispatcher_load_uses_cache_and_save_invalidates(tmp_path: Path) -> None:
    """End-to-end: load -> miss -> backend -> cache; second load is cached;
    save invalidates."""
    from context_broker.context_ttc.tasks import chat_cache
    from context_broker.server_ttc.tasks import context_tasks

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    state_holder: dict[str, object] = {}
    fake = _enable_redis_backend(state_holder)
    _enable_chat_cache(fake)
    context_tasks.CONTEXT_BACKEND = "redis"
    try:
        redis_tasks.save_redis_chat_context(
            session_id="cached-s",
            project_root=str(tmp_path),
            user_message="ping",
            assistant_message="pong",
        )
        # The save above bypasses the dispatcher, but the next load should miss
        # the cache first time and populate it.
        first = context_tasks._load(
            session_id="cached-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert first["cached"] is False
        assert first["message_count"] == 2

        second = context_tasks._load(
            session_id="cached-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert second["cached"] is True
        assert second["message_count"] == 2

        # Now save through the dispatcher — invalidates prior cache entries
        # AND warms the default-params signature with the fresh session (the
        # AUTO_WARM_CACHE_ON_SAVE default). So the next load with default
        # params is a cached hit AND reflects the new message count.
        context_tasks._save(
            session_id="cached-s",
            project_root=str(tmp_path),
            user_message="ping2",
            assistant_message="pong2",
        )
        third = context_tasks._load(
            session_id="cached-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert third["cached"] is True
        assert third["message_count"] == 4

        # A load with a NON-default signature still misses (invalidation
        # cleared every prior signature; only the default was re-warmed).
        fourth = context_tasks._load(
            session_id="cached-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="ping",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert fourth["cached"] is False
    finally:
        context_tasks.CONTEXT_BACKEND = original_backend
        _disable_chat_cache(original_url, original_ttl)
        _restore_backend(original_backend, original_url)


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------


def _write_env(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_env_loader_finds_nearest_env_walking_upward(tmp_path: Path) -> None:
    from context_broker import env_loader

    (tmp_path / "outer").mkdir()
    (tmp_path / "outer" / "inner").mkdir()
    _write_env(tmp_path / "outer" / ".env", "CONTEXT_BROKER_DASHBOARD_PORT=9999\n")
    assert env_loader.find_env_file(tmp_path / "outer" / "inner") == tmp_path / "outer" / ".env"


def test_env_loader_does_not_override_existing(tmp_path: Path) -> None:
    from context_broker import env_loader

    _write_env(
        tmp_path / ".env",
        "CB_TEST_NEW=fromfile\nCB_TEST_EXISTING=fromfile\n",
    )
    os.environ.pop("CB_TEST_NEW", None)
    os.environ["CB_TEST_EXISTING"] = "fromparent"
    try:
        applied = env_loader.load_env(tmp_path, quiet=True)
        assert applied == {"CB_TEST_NEW": "fromfile"}
        assert os.environ["CB_TEST_NEW"] == "fromfile"
        assert os.environ["CB_TEST_EXISTING"] == "fromparent"
    finally:
        os.environ.pop("CB_TEST_NEW", None)
        os.environ.pop("CB_TEST_EXISTING", None)


def test_env_loader_returns_empty_when_no_env_present(tmp_path: Path) -> None:
    from context_broker import env_loader

    assert env_loader.load_env(tmp_path, quiet=True) == {}


def test_env_loader_simple_parser_handles_comments_and_quotes(tmp_path: Path) -> None:
    from context_broker import env_loader

    body = """
# a comment
CB_SIMPLE_PLAIN=plain
CB_SIMPLE_QUOTED="hello world"
export CB_SIMPLE_EXPORTED=exported
CB_SIMPLE_TICK='ticked'
not-a-valid-line
"""
    p = tmp_path / ".env"
    _write_env(p, body)
    parsed = env_loader._parse_simple(p)
    assert parsed["CB_SIMPLE_PLAIN"] == "plain"
    assert parsed["CB_SIMPLE_QUOTED"] == "hello world"
    assert parsed["CB_SIMPLE_EXPORTED"] == "exported"
    assert parsed["CB_SIMPLE_TICK"] == "ticked"
    assert "not-a-valid-line" not in parsed


def test_module_entrypoint_can_disable_automatic_env_loading(tmp_path: Path) -> None:
    _write_env(tmp_path / ".env", "CB_TEST_ENTRYPOINT=fromfile\n")
    child_env = os.environ.copy()
    child_env.pop("CB_TEST_ENTRYPOINT", None)
    child_env["CONTEXT_BROKER_AUTO_LOAD_ENV"] = "0"
    child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; import context_broker.__main__; "
                "print(os.environ.get('CB_TEST_ENTRYPOINT', 'missing'))"
            ),
        ],
        cwd=tmp_path,
        env=child_env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "missing"


# ---------------------------------------------------------------------------
# Dashboard single-instance guard
# ---------------------------------------------------------------------------


def test_dashboard_guard_recognises_running_instance(monkeypatch_fixtures=None) -> None:
    """Probe returns our status banner → guard says "already running"."""
    import context_broker.__main__ as cli

    class _Resp:
        status = 200

        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    def _fake_urlopen(url, timeout=1.0):
        assert url.endswith("/api/status")
        return _Resp(b'{"backend":"redis"}')

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen  # type: ignore[assignment]
    try:
        assert cli._dashboard_already_running("127.0.0.1", 8770) is True
    finally:
        urllib.request.urlopen = original


def test_dashboard_guard_ignores_strangers_on_port() -> None:
    import context_broker.__main__ as cli

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return b'{"hello":"world"}'

    def _fake_urlopen(url, timeout=1.0):
        return _Resp()

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen  # type: ignore[assignment]
    try:
        assert cli._dashboard_already_running("127.0.0.1", 8770) is False
    finally:
        urllib.request.urlopen = original


def test_dashboard_guard_returns_false_on_connection_error() -> None:
    import urllib.error
    import urllib.request
    import context_broker.__main__ as cli

    def _fake_urlopen(url, timeout=1.0):
        raise urllib.error.URLError("nothing listening")

    original = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen  # type: ignore[assignment]
    try:
        assert cli._dashboard_already_running("127.0.0.1", 8770) is False
    finally:
        urllib.request.urlopen = original


# ---------------------------------------------------------------------------
# User identity resolver
# ---------------------------------------------------------------------------


def _reset_identity(use_account_name: bool = False, override: str = "") -> None:
    """Reflect new identity config into the loaded modules for tests."""
    from context_broker import identity

    config.USE_ACCOUNT_NAME = use_account_name
    config.ACCOUNT_NAME_OVERRIDE = override
    identity.USE_ACCOUNT_NAME = use_account_name
    identity.ACCOUNT_NAME_OVERRIDE = override


def test_identity_returns_default_when_feature_off() -> None:
    from context_broker import identity

    original = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    _reset_identity(False, "")
    try:
        assert identity.resolve_user_peer_id() == "user"
    finally:
        _reset_identity(*original)


def test_identity_explicit_argument_always_wins() -> None:
    from context_broker import identity

    original = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    _reset_identity(True, "override-name")
    try:
        assert identity.resolve_user_peer_id("explicit") == "explicit"
    finally:
        _reset_identity(*original)


def test_identity_override_takes_priority_over_getpass() -> None:
    from context_broker import identity

    original = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    _reset_identity(True, "alice@team")
    try:
        # "@" is sanitized to "-"
        assert identity.resolve_user_peer_id() == "alice-team"
    finally:
        _reset_identity(*original)


def test_identity_uses_account_name_when_toggle_on(monkeypatch=None) -> None:
    import getpass

    from context_broker import identity

    original = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    original_getuser = getpass.getuser
    _reset_identity(True, "")
    getpass.getuser = lambda: "ofir"  # type: ignore[assignment]
    try:
        assert identity.resolve_user_peer_id() == "ofir"
    finally:
        getpass.getuser = original_getuser  # type: ignore[assignment]
        _reset_identity(*original)


def test_identity_falls_back_when_getpass_fails() -> None:
    import getpass

    from context_broker import identity

    original = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    original_getuser = getpass.getuser

    def _boom():
        raise RuntimeError("no tty")

    _reset_identity(True, "")
    getpass.getuser = _boom  # type: ignore[assignment]
    try:
        assert identity.resolve_user_peer_id() == "user"
    finally:
        getpass.getuser = original_getuser  # type: ignore[assignment]
        _reset_identity(*original)


def test_redis_save_uses_resolved_account_name(tmp_path: Path) -> None:
    """End-to-end: when account-name is enabled, the user peer id stored in
    Redis is the OS account name, not the literal 'user'."""
    import getpass

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_identity = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    original_getuser = getpass.getuser
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    _reset_identity(True, "")
    getpass.getuser = lambda: "ofir"  # type: ignore[assignment]
    try:
        payload = redis_tasks.save_redis_chat_context(
            session_id="acct-s",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi",
        )
        assert payload["user_peer_id"] == "ofir"
        # Assistant peer untouched
        assert payload["assistant_peer_id"] == "assistant"

        loaded = redis_tasks.load_redis_chat_context(
            session_id="acct-s", project_root=str(tmp_path)
        )
        peers = {m["peer_id"] for m in loaded["messages"]}
        assert peers == {"ofir", "assistant"}
    finally:
        getpass.getuser = original_getuser  # type: ignore[assignment]
        _reset_identity(*original_identity)
        _restore_backend(original_backend, original_url)


def test_redis_save_explicit_user_peer_overrides_account_name(tmp_path: Path) -> None:
    import getpass

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_identity = (config.USE_ACCOUNT_NAME, config.ACCOUNT_NAME_OVERRIDE)
    original_getuser = getpass.getuser
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    _reset_identity(True, "")
    getpass.getuser = lambda: "ofir"  # type: ignore[assignment]
    try:
        payload = redis_tasks.save_redis_chat_context(
            session_id="explicit-s",
            project_root=str(tmp_path),
            user_message="hello",
            user_peer_id="caller-supplied",
        )
        assert payload["user_peer_id"] == "caller-supplied"
    finally:
        getpass.getuser = original_getuser  # type: ignore[assignment]
        _reset_identity(*original_identity)
        _restore_backend(original_backend, original_url)


# ---------------------------------------------------------------------------
# Append semantics + JSON chat ledger + cross-session retrieval
# ---------------------------------------------------------------------------


def _point_storage_at(tmp_path: Path) -> tuple[str, str]:
    """Redirect global+in-project storage under tmp_path so ledger tests are
    isolated. Returns (original_base, original_mode) to restore later."""
    from context_broker.context_ttc.tasks import chat_ledger as ledger_mod

    original_base = config.STORAGE_BASE_DIR
    original_mode = config.STORAGE_MODE
    base = tmp_path / "global"
    base.mkdir(exist_ok=True)
    config.STORAGE_BASE_DIR = str(base)
    config.STORAGE_MODE = "both"
    ledger_mod.STORAGE_BASE_DIR = str(base)
    ledger_mod.STORAGE_MODE = "both"
    return original_base, original_mode


def _restore_storage(original_base: str, original_mode: str) -> None:
    from context_broker.context_ttc.tasks import chat_ledger as ledger_mod

    config.STORAGE_BASE_DIR = original_base
    config.STORAGE_MODE = original_mode
    ledger_mod.STORAGE_BASE_DIR = original_base
    ledger_mod.STORAGE_MODE = original_mode


def test_redis_save_appends_does_not_overwrite(tmp_path: Path) -> None:
    """Two saves to the same session must accumulate, not replace."""
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    try:
        redis_tasks.save_redis_chat_context(
            session_id="s",
            project_root=str(tmp_path),
            user_message="first user",
            assistant_message="first assistant",
        )
        redis_tasks.save_redis_chat_context(
            session_id="s",
            project_root=str(tmp_path),
            user_message="second user",
            assistant_message="second assistant",
        )
        loaded = redis_tasks.load_redis_chat_context(
            session_id="s", project_root=str(tmp_path)
        )
        contents = [m["content"] for m in loaded["messages"]]
        assert loaded["message_count"] == 4
        assert contents == [
            "first user",
            "first assistant",
            "second user",
            "second assistant",
        ]
    finally:
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_chat_ledger_appends_to_local_json(tmp_path: Path) -> None:
    from context_broker.context_ttc.tasks import chat_ledger

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    try:
        result = redis_tasks.save_redis_chat_context(
            session_id="ledger-s",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi back",
        )
        assert result["ledger_files"]
        # After first save, ledger has 2 messages
        ledger = chat_ledger.read_ledger(str(tmp_path), "ledger-s")
        assert ledger is not None
        assert len(ledger["messages"]) == 2

        # Second save APPENDS
        redis_tasks.save_redis_chat_context(
            session_id="ledger-s",
            project_root=str(tmp_path),
            user_message="more",
            assistant_message="okay",
        )
        ledger = chat_ledger.read_ledger(str(tmp_path), "ledger-s")
        assert ledger is not None
        assert len(ledger["messages"]) == 4
        contents = [m["content"] for m in ledger["messages"]]
        assert contents == ["hello", "hi back", "more", "okay"]

        # File path is project-digest scoped
        digest = chat_ledger._digest(str(tmp_path))
        for path in result["ledger_files"]:
            assert digest in path
            assert path.endswith("ledger-s.json")
    finally:
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_cross_session_matches_finds_important_across_sessions(tmp_path: Path) -> None:
    """Save to two sessions and retrieve only the matching turns across both."""
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    try:
        redis_tasks.save_redis_chat_context(
            session_id="s-a",
            project_root=str(tmp_path),
            user_message="how do I configure redis",
            assistant_message="set CONTEXT_BROKER_REDIS_URL",
        )
        redis_tasks.save_redis_chat_context(
            session_id="s-b",
            project_root=str(tmp_path),
            user_message="unrelated thing",
            assistant_message="unrelated answer",
        )
        redis_tasks.save_redis_chat_context(
            session_id="s-b",
            project_root=str(tmp_path),
            user_message="redis cache TTL",
            assistant_message="default is 300 seconds",
        )

        out = redis_tasks.load_cross_session_matches(
            project_root=str(tmp_path),
            search_query="redis",
            top_k=10,
        )
        assert out["sessions_scanned"] == 2
        # Matches: "configure redis", "set CONTEXT_BROKER_REDIS_URL", "redis cache TTL"
        # = 3 messages across both sessions
        assert out["total_matches"] == 3
        sessions_in_matches = {m["session_id"] for m in out["matches"]}
        assert sessions_in_matches == {"s-a", "s-b"}

        # top_k=1 returns only the most recent
        capped = redis_tasks.load_cross_session_matches(
            project_root=str(tmp_path),
            search_query="redis",
            top_k=1,
        )
        assert capped["match_count"] == 1
        assert capped["matches"][0]["session_id"] == "s-b"
    finally:
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_chat_ledger_survives_when_messages_empty(tmp_path: Path) -> None:
    from context_broker.context_ttc.tasks import chat_ledger

    written = chat_ledger.append_turn(str(tmp_path), "s", [])
    assert written == []


# ---------------------------------------------------------------------------
# Warm-on-save default + bulk record_session
# ---------------------------------------------------------------------------


def test_save_warms_cache_so_next_load_is_cached_hit(tmp_path: Path) -> None:
    """Default behavior: after save_chat_context, the next load_chat_context
    (default params) must be a cached hit, not a miss-then-fill round trip."""
    from context_broker.context_ttc.tasks import chat_cache
    from context_broker.server_ttc.tasks import context_tasks

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    original_warm = config.AUTO_WARM_CACHE_ON_SAVE
    state_holder: dict[str, object] = {}
    orig_base, orig_mode = _point_storage_at(tmp_path)
    fake = _enable_redis_backend(state_holder)
    _enable_chat_cache(fake)
    context_tasks.CONTEXT_BACKEND = "redis"
    context_tasks.AUTO_WARM_CACHE_ON_SAVE = True
    config.AUTO_WARM_CACHE_ON_SAVE = True
    try:
        result = context_tasks._save(
            session_id="warm-s",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi",
        )
        assert result["cache_warmed"] is True

        # The very next load (default params) must hit the cache.
        first = context_tasks._load(
            session_id="warm-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert first["cached"] is True
        assert first["message_count"] == 2

        # A load with a different signature (search_query) must NOT be cached
        # — that signature was invalidated and isn't warmed by default.
        second = context_tasks._load(
            session_id="warm-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="hello",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert second["cached"] is False
    finally:
        config.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.CONTEXT_BACKEND = original_backend
        _disable_chat_cache(original_url, original_ttl)
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_save_can_disable_warm_via_flag(tmp_path: Path) -> None:
    """When AUTO_WARM_CACHE_ON_SAVE is false, behavior reverts to invalidate-only."""
    from context_broker.context_ttc.tasks import chat_cache
    from context_broker.server_ttc.tasks import context_tasks

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    original_warm = config.AUTO_WARM_CACHE_ON_SAVE
    state_holder: dict[str, object] = {}
    orig_base, orig_mode = _point_storage_at(tmp_path)
    fake = _enable_redis_backend(state_holder)
    _enable_chat_cache(fake)
    context_tasks.CONTEXT_BACKEND = "redis"
    context_tasks.AUTO_WARM_CACHE_ON_SAVE = False
    config.AUTO_WARM_CACHE_ON_SAVE = False
    try:
        result = context_tasks._save(
            session_id="nowarm-s",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi",
        )
        assert result["cache_warmed"] is False

        first = context_tasks._load(
            session_id="nowarm-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        # Cache is not pre-warmed → first load is a miss
        assert first["cached"] is False
    finally:
        config.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.CONTEXT_BACKEND = original_backend
        _disable_chat_cache(original_url, original_ttl)
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_record_session_bulk_save(tmp_path: Path) -> None:
    """record_session-style bulk save persists every turn in one shot and the
    full session is immediately readable from the cache."""
    from context_broker.context_ttc.tasks import chat_cache
    from context_broker.server_ttc.tasks import context_tasks

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    original_ttl = chat_cache.CHAT_CACHE_TTL_SECONDS
    original_warm = config.AUTO_WARM_CACHE_ON_SAVE
    state_holder: dict[str, object] = {}
    orig_base, orig_mode = _point_storage_at(tmp_path)
    fake = _enable_redis_backend(state_holder)
    _enable_chat_cache(fake)
    context_tasks.CONTEXT_BACKEND = "redis"
    context_tasks.AUTO_WARM_CACHE_ON_SAVE = True
    config.AUTO_WARM_CACHE_ON_SAVE = True
    try:
        turns = [
            {"user": f"q{i}", "assistant": f"a{i}"} for i in range(5)
        ]
        # Same loop record_session does, but invoked at the helper level
        total = 0
        for turn in turns:
            payload = context_tasks._save(
                session_id="bulk-s",
                project_root=str(tmp_path),
                user_message=turn["user"],
                assistant_message=turn["assistant"],
            )
            total += int(payload["messages_saved"])
        assert total == 10  # 5 turns × 2 messages

        loaded = context_tasks._load(
            session_id="bulk-s",
            project_root=str(tmp_path),
            tokens=0,
            summary=True,
            search_query="",
            limit_to_session=True,
            user_peer_id="",
            assistant_peer_id="",
        )
        assert loaded["cached"] is True
        assert loaded["message_count"] == 10
        contents = [m["content"] for m in loaded["messages"]]
        # Order preserved across all 5 turns
        assert contents == [
            "q0", "a0", "q1", "a1", "q2", "a2", "q3", "a3", "q4", "a4",
        ]
    finally:
        config.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.AUTO_WARM_CACHE_ON_SAVE = original_warm
        context_tasks.CONTEXT_BACKEND = original_backend
        _disable_chat_cache(original_url, original_ttl)
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


# ---------------------------------------------------------------------------
# Per-user activity tracking
# ---------------------------------------------------------------------------


def test_user_activity_accumulates_across_saves(tmp_path: Path) -> None:
    """Three saves with the same user peer must record three timestamped
    request entries and update first_seen / last_seen / request_count."""
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    try:
        for index in range(3):
            redis_tasks.save_redis_chat_context(
                session_id=f"ua-s-{index}",
                project_root=str(tmp_path),
                user_message=f"q{index}",
                assistant_message=f"a{index}",
                user_peer_id="alice",
            )

        users = redis_tasks.list_users(redis_tasks.project_digest(str(tmp_path)))
        alice = next(u for u in users if u["peer_id"] == "alice")
        assert alice["request_count"] == 3
        assert alice["request_log_length"] == 3
        assert alice["first_seen"] > 0
        assert alice["last_seen"] >= alice["first_seen"]

        activity = redis_tasks.load_user_activity(
            redis_tasks.project_digest(str(tmp_path)),
            "alice",
        )
        assert activity["request_count"] == 3
        assert len(activity["requests"]) == 3
        sessions = [r["session_id"] for r in activity["requests"]]
        assert sessions == ["ua-s-0", "ua-s-1", "ua-s-2"]
        # Timestamps are non-decreasing
        timestamps = [r["timestamp"] for r in activity["requests"]]
        assert timestamps == sorted(timestamps)
    finally:
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_user_activity_lists_multiple_users(tmp_path: Path) -> None:
    """Two different user peers should both surface in list_users."""
    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    try:
        redis_tasks.save_redis_chat_context(
            session_id="s-1",
            project_root=str(tmp_path),
            user_message="hi from alice",
            user_peer_id="alice",
        )
        redis_tasks.save_redis_chat_context(
            session_id="s-2",
            project_root=str(tmp_path),
            user_message="hi from bob",
            user_peer_id="bob",
        )

        users = {
            u["peer_id"]: u
            for u in redis_tasks.list_users(redis_tasks.project_digest(str(tmp_path)))
        }
        # Note: the assistant peer ("assistant") is also tracked because the
        # save call records activity for whichever peers actually spoke.
        assert "alice" in users and "bob" in users
        assert users["alice"]["request_count"] == 1
        assert users["bob"]["request_count"] == 1
    finally:
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


def test_dashboard_user_activity_routes(tmp_path: Path) -> None:
    """End-to-end Starlette routes for the per-user audit trail."""
    from starlette.testclient import TestClient

    original_backend = config.CONTEXT_BACKEND
    original_url = config.REDIS_URL
    orig_base, orig_mode = _point_storage_at(tmp_path)
    state_holder: dict[str, object] = {}
    _enable_redis_backend(state_holder)
    data_tasks.CONTEXT_BACKEND = "redis"
    try:
        redis_tasks.save_redis_chat_context(
            session_id="dash-s",
            project_root=str(tmp_path),
            user_message="hello",
            assistant_message="hi",
            user_peer_id="charlie",
        )
        digest = redis_tasks.project_digest(str(tmp_path))
        client = TestClient(create_app())

        r = client.get(f"/api/projects/{digest}/users")
        assert r.status_code == 200
        body = r.json()
        assert body["backend"] == "redis"
        peers = {u["peer_id"] for u in body["users"]}
        assert "charlie" in peers

        r = client.get(f"/api/projects/{digest}/users/charlie")
        assert r.status_code == 200
        body = r.json()
        assert body["peer_id"] == "charlie"
        assert body["request_count"] == 1
        assert body["requests"][0]["session_id"] == "dash-s"
        assert body["requests"][0]["timestamp"] > 0

        r = client.get(f"/projects/{digest}/users")
        assert r.status_code == 200
        assert "charlie" in r.text

        r = client.get(f"/projects/{digest}/users/charlie")
        assert r.status_code == 200
        assert "Request log" in r.text
        assert "dash-s" in r.text
    finally:
        data_tasks.CONTEXT_BACKEND = original_backend
        _restore_storage(orig_base, orig_mode)
        _restore_backend(original_backend, original_url)


# Smoke: validate the JSON shape used by the templates does not crash render
def test_templates_render_with_empty_collections() -> None:
    from context_broker.dashboard_ttc.tools import templates

    assert "No projects" in templates.render_projects_page([], backend="redis")
    assert "No sessions" in templates.render_project_page("d1", [], backend="redis")
    empty_session = {"project": {"digest": "d1", "name": "demo"}, "session_id": "s", "messages": []}
    assert "No messages" in templates.render_messages_page(empty_session, backend="redis")
    # JSON round-trip sanity
    json.dumps(empty_session)
