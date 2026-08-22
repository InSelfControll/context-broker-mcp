"""Tests for streamed progress callbacks during indexing and search."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np

from context_broker.indexer_ttc.tasks import index_tasks, search_tasks
from context_broker.indexer_ttc.tools import index_cache_tools, state
from context_broker.server_ttc.tools import helpers


def _patch_ignore_dirs(monkeypatch) -> None:
    """Allow pytest tmp_path projects (under /tmp) to be walked."""
    from context_broker.config import DEFAULT_IGNORE_DIRS

    cleaned = DEFAULT_IGNORE_DIRS - {"tmp", "temp"}
    monkeypatch.setattr(
        "context_broker.indexer_ttc.tools.collect_tools.DEFAULT_IGNORE_DIRS",
        cleaned,
    )
    monkeypatch.setattr(index_tasks, "DEFAULT_IGNORE_DIRS", cleaned)


class _FakeModel:
    def encode(self, docs, **kwargs):
        if isinstance(docs, str):
            docs = [docs]
        return np.asarray(
            [[float(len(d) % 7) + 1.0, 1.0] for d in docs], dtype=np.float32
        )


class _FakeEncoder:
    def encode(self, text: str):
        return text.split()


def _fresh_project(tmp_path: Path, monkeypatch) -> str:
    _patch_ignore_dirs(monkeypatch)
    monkeypatch.setattr(index_cache_tools, "INDEX_DISK_CACHE_ENABLED", False)
    (tmp_path / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    state.INDEXES.clear()
    state.QUERY_CACHE.clear()
    monkeypatch.setattr(index_tasks, "get_model", lambda: _FakeModel())
    monkeypatch.setattr(index_tasks, "get_encoder", lambda: _FakeEncoder())
    monkeypatch.setattr(search_tasks, "persist_token_report", lambda *a, **k: None)
    return str(tmp_path)


def test_index_progress_callback_receives_stages(tmp_path: Path, monkeypatch) -> None:
    root = _fresh_project(tmp_path, monkeypatch)
    messages: list[str] = []

    idx = index_tasks.get_index_for_project(root, progress_callback=messages.append)

    assert idx is not None
    assert any("Collecting project files" in m for m in messages)
    assert any("Reading 1 files" in m for m in messages)
    assert any("Embedding 1 files" in m for m in messages)
    state.INDEXES.clear()


def test_index_progress_callback_none_is_safe(tmp_path: Path, monkeypatch) -> None:
    root = _fresh_project(tmp_path, monkeypatch)
    idx = index_tasks.get_index_for_project(root)
    assert idx is not None
    state.INDEXES.clear()


def test_index_progress_callback_errors_do_not_break_indexing(
    tmp_path: Path, monkeypatch
) -> None:
    root = _fresh_project(tmp_path, monkeypatch)

    def _boom(_msg: str) -> None:
        raise RuntimeError("callback exploded")

    idx = index_tasks.get_index_for_project(root, progress_callback=_boom)
    assert idx is not None
    state.INDEXES.clear()


def test_search_progress_callback_receives_scoring_stage(
    tmp_path: Path, monkeypatch
) -> None:
    root = _fresh_project(tmp_path, monkeypatch)
    messages: list[str] = []

    result = search_tasks.search_codebase(
        "foo", root, top_k=3, progress_callback=messages.append
    )

    assert result["returned_files"] >= 1
    assert any("Scoring" in m for m in messages)
    state.INDEXES.clear()
    state.QUERY_CACHE.clear()


def test_stream_progress_no_ctx_or_no_loop_is_noop() -> None:
    helpers.stream_progress(None, "ignored")
    helpers.stream_progress(object(), "no running loop")  # must not raise


def test_stream_progress_schedules_on_running_loop(monkeypatch) -> None:
    monkeypatch.setattr(helpers, "ENABLE_PROGRESS_NOTIFICATIONS", True)
    received: list[str] = []

    class _FakeCtx:
        async def info(self, message: str) -> None:
            received.append(message)

    async def _run() -> None:
        helpers.stream_progress(_FakeCtx(), "stage message")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_run())
    assert received == ["stage message"]
