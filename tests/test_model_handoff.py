"""Cross-model context preservation, project isolation, and explicit failure gates."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastmcp import Client

from context_broker.context_ttc.tasks import handoff_tasks as handoffs


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(handoffs, "STORAGE_BASE_DIR", str(tmp_path / "store"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "source.py").write_text("value = 42\n")
    return dict(
        project_root=str(root),
        source_model="model-a",
        session_id="codex-session",
        files=["source.py"],
        state={
            "goal": "Preserve existing API",
            "messages": [{"role": "user", "content": "שלום 👋"}],
            "decisions": ["Keep storage local"],
            "constraints": ["Medium reasoning only"],
            "facts": ["Laptop integration works"],
            "tasks": [
                {"task": "Native check", "status": "failed", "failure_reason": "Host absent"}
            ],
            "acceptance_criteria": ["All regressions pass"],
            "open_questions": ["Cursor version?"],
        },
    )


def test_exact_memory_survives_model_switch_and_fresh_disk_read(setup):
    saved = handoffs.save_handoff(**setup)
    for model in ["model-b", "model-c"]:
        loaded = handoffs.load_handoff(setup["project_root"], saved["handoff_id"], model)
        state = loaded["checkpoint"]["state"]
        for key in ["messages", "decisions", "constraints", "facts", "open_questions"]:
            assert state[key] == setup["state"][key]
        assert state["tasks"][0]["status"] == "failed"
        assert state["tasks"][0]["failure_reason"] == "Host absent"
        assert loaded["checkpoint"]["files"] == {"source.py": "value = 42\n"}
        assert loaded["completed"] is False


def test_concurrent_identical_saves_deduplicate_without_overwriting(setup):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: handoffs.save_handoff(**setup), range(8)))
    assert len({r["handoff_id"] for r in results}) == 1
    assert len(list(handoffs.Path(handoffs.STORAGE_BASE_DIR).rglob("*.json"))) == 1


def test_project_isolation_and_no_path_traversal(setup, tmp_path):
    saved = handoffs.save_handoff(**setup)
    other = tmp_path / "other" / "project"
    other.mkdir(parents=True)
    with pytest.raises(ValueError, match="not found"):
        handoffs.load_handoff(str(other), saved["handoff_id"], "b")
    with pytest.raises(ValueError, match="Invalid handoff"):
        handoffs.load_handoff(setup["project_root"], "../secret", "b")


def test_stale_and_oversized_loads_never_lose_saved_context(setup):
    saved = handoffs.save_handoff(**setup)
    with pytest.raises(ValueError, match="Nothing truncated"):
        handoffs.load_handoff(setup["project_root"], saved["handoff_id"], "b", 1)
    (handoffs.Path(setup["project_root"]) / "source.py").write_text("changed = True\n")
    with pytest.raises(ValueError, match="files changed"):
        handoffs.load_handoff(setup["project_root"], saved["handoff_id"], "b")
    stored = json.loads(
        handoffs.handoff_path(setup["project_root"], saved["handoff_id"]).read_text()
    )
    assert stored["files"]["source.py"] == "value = 42\n"


def test_corrupt_checkpoint_cannot_be_loaded_or_overwritten(setup):
    saved = handoffs.save_handoff(**setup)
    path = handoffs.handoff_path(setup["project_root"], saved["handoff_id"])
    payload = json.loads(path.read_text())
    payload["state"]["goal"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        handoffs.load_handoff(setup["project_root"], saved["handoff_id"], "b")
    with pytest.raises(ValueError, match="corrupt"):
        handoffs.save_handoff(**setup)


@pytest.mark.parametrize(
    "item",
    [
        {"task": "a", "status": "failed"},
        {"task": "a", "status": "completed", "failure_reason": "still broken", "evidence": ["x"]},
        {"task": "a", "status": "completed"},
    ],
)
def test_invalid_task_outcomes_rejected(setup, item):
    setup["state"]["tasks"] = [item]
    with pytest.raises(ValueError):
        handoffs.save_handoff(**setup)


def test_secrets_rejected_before_persistence(setup):
    setup["state"]["facts"] = ["-----BEGIN " + "PRIVATE KEY-----"]
    with pytest.raises(ValueError, match="secrets"):
        handoffs.save_handoff(**setup)
    assert not handoffs.Path(handoffs.STORAGE_BASE_DIR).exists()


@pytest.mark.anyio
async def test_two_mcp_clients_restore_memory_and_report_load_failure(setup):
    from context_broker.server import create_mcp_server

    async with Client(create_mcp_server()) as first:
        saved = await first.call_tool("save_model_handoff", setup)
    async with Client(create_mcp_server()) as second:
        args = {
            "project_root": setup["project_root"],
            "handoff_id": saved.data["handoff_id"],
            "target_model": "new-model",
        }
        loaded = await second.call_tool("load_model_handoff", args)
        assert loaded.data["checkpoint"]["state"]["messages"] == setup["state"]["messages"]
        failed = await second.call_tool_mcp("load_model_handoff", {**args, "max_bytes": 1})
        assert failed.isError and failed.structuredContent["status"] == "failed"
        assert "Nothing truncated" in failed.structuredContent["failure_reason"]
