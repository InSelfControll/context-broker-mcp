"""Selective issue memory, explicit indexing consent, and bounded direct reads."""

import json
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from context_broker.context_ttc.tasks import history_tasks as history
from context_broker.context_ttc.tools.identity_tools import project_digest
from context_broker.server_ttc.tasks.history_tasks import register_history_tools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(history, "STORAGE_BASE_DIR", str(tmp_path / "storage"))
    folder = Path(history.STORAGE_BASE_DIR) / "chats" / project_digest(str(root))
    folder.mkdir(parents=True)
    (folder / "one.json").write_text(
        json.dumps(
            {
                "messages": [
                    {"peer_id": "user", "content": "Redis connection timeout on startup"},
                    {
                        "peer_id": "assistant",
                        "content": "Previously fixed by correcting the Redis port; verify current config.",
                    },
                    {"peer_id": "user", "content": "Change the landing page colors"},
                ]
            }
        )
    )
    return str(root), folder


def test_unrelated_and_generic_questions_inject_nothing(project):
    root, _ = project
    for query in ["fix this issue again please", "repair avatar image cropping"]:
        result = history.lookup_history(root, query)
        assert result["matches"] == []
        assert result["index"] is False and result["choice_required"]
    assert not list(Path(history.STORAGE_BASE_DIR).rglob("*.sqlite3"))


def test_no_index_reads_new_history_and_keeps_answer_small(project):
    root, folder = project
    history.set_history_policy(root, False)
    result = history.lookup_history(root, "Redis startup timeout")
    assert len(result["matches"]) == 1
    assert "correcting the Redis port" in result["matches"][0]["text"]
    assert "landing" not in str(result)
    (folder / "two.json").write_text(
        json.dumps(
            {
                "messages": [
                    {"content": "Database migration deadlock resolved by consistent lock ordering"}
                ]
            }
        )
    )
    assert history.lookup_history(root, "migration database deadlock")["matches"]
    assert not list(Path(history.STORAGE_BASE_DIR).rglob("*.sqlite3"))


def test_index_reuses_unchanged_records_and_refreshes_changes(project, monkeypatch):
    root, folder = project
    history.set_history_policy(root, True)
    expected = history.lookup_history(root, "Redis startup timeout")["matches"]
    original = history._records
    reads = []

    def track(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(history, "_records", track)
    assert history.lookup_history(root, "Redis startup timeout")["matches"] == expected
    assert reads == []
    (folder / "one.json").write_text(json.dumps({"messages": [{"content": "New unrelated issue"}]}))
    assert not history.lookup_history(root, "Redis startup timeout")["matches"]
    assert len(reads) == 1
    history.set_history_policy(root, False)
    assert not list(Path(history.STORAGE_BASE_DIR).rglob("*.sqlite3"))
    assert (folder / "one.json").exists()


def test_project_isolation_secret_filter_and_scan_failure(project, tmp_path):
    root, folder = project
    other = tmp_path / "other" / "project"
    other.mkdir(parents=True)
    assert history.lookup_history(str(other), "Redis startup timeout")["matches"] == []
    (folder / "secret.json").write_text(
        json.dumps({"messages": [{"content": "Redis startup timeout -----BEGIN PRIVATE KEY-----"}]})
    )
    (folder / "broken.json").write_text("{broken")
    result = history.lookup_history(root, "Redis startup timeout")
    assert "PRIVATE KEY" not in str(result)
    assert result["partial"] and result["skipped_files"] == 1


@pytest.mark.anyio
async def test_consent_and_automatic_retrieval_without_session_preload(project):
    root, _ = project
    server = FastMCP("history test")
    register_history_tools(server)

    @server.tool()
    def route_task(task: str, project_root: str):
        return {"task": task}

    questions = []

    async def answer(message, response_type, params, context):
        questions.append(message)
        return {"value": "Index"}

    async with Client(server, elicitation_handler=answer) as client:
        await client.list_tools()
        assert not questions
        assert not list(Path(history.STORAGE_BASE_DIR).rglob("*.sqlite3"))
        configured = await client.call_tool("configure_history_indexing", {"project_root": root})
        assert configured.data["index"] and questions
        unrelated = await client.call_tool(
            "route_task", {"task": "avatar cropping", "project_root": root}
        )
        assert len(unrelated.content) == 1
        related = await client.call_tool(
            "route_task", {"task": "Redis startup timeout", "project_root": root}
        )
        assert len(related.content) == 2
        assert "correcting the Redis port" in related.content[-1].text


@pytest.mark.anyio
async def test_declined_consent_does_not_enable_index(project):
    root, _ = project
    server = FastMCP("consent test")
    register_history_tools(server)

    async def decline(*args):
        from fastmcp.client.elicitation import ElicitResult

        return ElicitResult(action="decline")

    async with Client(server, elicitation_handler=decline) as client:
        result = await client.call_tool(
            "configure_history_indexing", {"project_root": root}, raise_on_error=False
        )
    assert not history.history_policy(root)["index"]
    assert result.data["status"] == "unchanged"
