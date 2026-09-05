"""Regression coverage for storage, routing, and security boundaries."""

from pathlib import Path

import pytest

from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.router_ttc.tasks import router_tasks
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor, ToolRegistry
from context_broker.router_ttc.tools.safety_tools import redact_secrets
from context_broker.storage_ttc.tasks import json_tasks
from context_broker.storage_ttc.tools import path_tools


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(path_tools, "STORAGE_BASE_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(path_tools, "STORAGE_MODE", "global")
    monkeypatch.setattr(json_tasks, "STORAGE_MODE", "global")
    return tmp_path


@pytest.mark.parametrize("field", ["filename", "project_name", "subdir"])
@pytest.mark.parametrize("bad_path", ["../outside", "/tmp/outside", "..\\outside"])
def test_storage_rejects_paths_outside_its_namespace(storage, field, bad_path):
    if bad_path.startswith("/"):
        bad_path = str(storage / "outside")
    arguments = {"project_name": "demo", "filename": "saved", "subdir": ""}
    arguments[field] = bad_path
    with pytest.raises(ValueError):
        json_tasks.save_json_data(**arguments, data={"message": "sample"})
    with pytest.raises(ValueError):
        json_tasks.load_json_data(**arguments)


def test_storage_rejects_symlink_escape(storage):
    base = storage / "store" / "demo"
    base.mkdir(parents=True)
    outside = storage / "outside.json"
    outside.write_text('{"original": true}')
    (base / "saved.json").symlink_to(outside)
    with pytest.raises(ValueError):
        json_tasks.save_json_data("demo", "saved", {"overwrite": True})
    with pytest.raises(ValueError):
        json_tasks.load_json_data("demo", "saved")
    assert outside.read_text() == '{"original": true}'


def test_failed_serialization_preserves_previous_save(storage):
    path = Path(json_tasks.save_json_data("demo", "saved", {"original": True}))
    with pytest.raises(TypeError):
        json_tasks.save_json_data("demo", "saved", {"invalid": object()})
    assert json_tasks.load_json_data("demo", "saved") == {"original": True}
    assert path.exists()


def test_in_project_mode_lists_global_fallback_without_root(storage, monkeypatch):
    monkeypatch.setattr(path_tools, "STORAGE_MODE", "in-project")
    monkeypatch.setattr(json_tasks, "STORAGE_MODE", "in-project")
    json_tasks.save_json_data("demo", "saved", {})
    assert json_tasks.list_saved_json("demo") == ["saved.json"]


def test_secret_scan_covers_entire_returned_content(tmp_path):
    path = tmp_path / "settings.txt"
    path.write_text("ordinary setting\n" * 400 + "API_KEY=example-test-value\n")
    assert read_file_content(str(path), max_chars=20_000) is None


def test_redaction_uses_nested_sensitive_keys():
    payload = {
        "nested": [{"password": "ordinary-value", "api_key": "another-value"}],
        "query": "find a password reset handler",
    }
    redacted = redact_secrets(payload)
    assert redacted["nested"] == [{"password": "[REDACTED]", "api_key": "[REDACTED]"}]
    assert redacted["query"] == payload["query"]


def test_literal_routing_with_zero_top_k_is_empty(tmp_path):
    registry = ToolRegistry(tmp_path)
    registry.register(ToolDescriptor(id="find_in_codebase", name="find_in_codebase"))
    result = router_tasks.route_task("exact", registry=registry, top_k=0)
    assert result["selected_tools"] == []


def test_router_never_exceeds_token_budget(tmp_path):
    registry = ToolRegistry(tmp_path)
    registry.register(ToolDescriptor(id="search", name="search", description="search code"))
    result = router_tasks.route_task("search", registry=registry, token_budget=1)
    assert result["selected_tools"] == []
    assert result["token_report"]["within_budget"] is True


def test_route_results_cannot_mutate_cached_plan(tmp_path):
    registry = ToolRegistry(tmp_path)
    registry.register(ToolDescriptor(id="cache-test", name="cache-test"))
    first = router_tasks.route_task("cache-test", registry=registry)
    first["plan"]["nodes"].clear()
    second = router_tasks.route_task("cache-test", registry=registry)
    assert len(second["plan"]["nodes"]) == 1
    second["selected_tools"].clear()
    assert len(router_tasks.route_task("cache-test", registry=registry)["selected_tools"]) == 1


def test_downstream_rediscovery_removes_deleted_tools(tmp_path):
    registry = ToolRegistry(tmp_path)
    registry.register(ToolDescriptor(id="other.tool", name="tool", server="other"))
    registry.ingest_downstream_capabilities({"server": "remote", "tools": [{"name": "old"}]})
    registry.ingest_downstream_capabilities({"server": "remote", "tools": [{"name": "new"}]})
    reloaded = ToolRegistry(tmp_path)
    assert reloaded.load_cache()
    assert reloaded.get("remote.old") is None
    assert reloaded.get("remote.new") is not None
    assert reloaded.get("other.tool") is not None


def test_router_plan_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(router_tasks, "ROUTER_PLAN_CACHE_MAX_ENTRIES", 2)
    registry = ToolRegistry(tmp_path)
    registry.register(ToolDescriptor(id="bounded", name="bounded"))
    for number in range(5):
        router_tasks.route_task(f"bounded {number}", registry=registry)
    assert len(router_tasks._PLAN_CACHE) <= 2
    assert router_tasks.route_task("bounded 0", registry=registry)["cached"] is False


def test_concurrent_ledger_appends_preserve_all_messages(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from context_broker.context_ttc.tasks import chat_ledger

    monkeypatch.setattr(chat_ledger, "STORAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(chat_ledger, "STORAGE_MODE", "global")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda n: chat_ledger.append_turn("project", "session", [{"content": str(n)}]),
                range(40),
            )
        )
    payload = chat_ledger.read_ledger("project", "session")
    assert sorted(int(message["content"]) for message in payload["messages"]) == list(range(40))


def test_corrupt_ledger_is_not_overwritten(tmp_path, monkeypatch):
    from context_broker.context_ttc.tasks import chat_ledger

    monkeypatch.setattr(chat_ledger, "STORAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(chat_ledger, "STORAGE_MODE", "global")
    path = chat_ledger.ledger_paths("project", "session")[0]
    path.parent.mkdir(parents=True)
    path.write_text('{"messages": [')
    with pytest.raises(ValueError):
        chat_ledger.append_turn("project", "session", [{"content": "new"}])
    assert path.read_text() == '{"messages": ['
