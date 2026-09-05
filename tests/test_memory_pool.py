"""Shared-resource allocation, concurrency, and project isolation tests."""

from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading
import time

from context_broker.indexer_ttc.tools.memory_pool import MemoryPool
from context_broker.indexer_ttc.tools import model_tools, state


def test_namespaces_share_one_budget_without_sharing_values():
    pool = MemoryPool(1200)
    projects = pool.namespace("indexes")
    chats = pool.namespace("queries")
    projects["a"] = "A" * 350
    chats["a"] = "B" * 350
    assert projects["a"] != chats["a"]
    projects["b"] = "C" * 350
    assert pool.snapshot()["retained_bytes"] <= 1200
    assert pool.snapshot()["evictions"] > 0


def test_oversized_payload_is_usable_but_not_retained():
    pool = MemoryPool(200)
    cache = pool.namespace("indexes")
    cache["project"] = "large" * 1000
    assert "project" not in cache
    assert pool.used_bytes == 0


def test_model_initializes_once_across_concurrent_sessions(monkeypatch):
    monkeypatch.setattr(state, "SHARED_MODEL", None)
    monkeypatch.setattr(model_tools, "MODEL_LOCAL_ONLY", False)
    calls = []
    sentinel = object()

    def load(**kwargs):
        calls.append(kwargs)
        time.sleep(0.03)
        return sentinel

    class Runtime:
        def set_num_threads(self, count):
            pass

        def set_num_interop_threads(self, count):
            pass

    monkeypatch.setattr(model_tools, "torch", Runtime())
    monkeypatch.setattr(model_tools, "_create_model", load)
    start = threading.Barrier(6)

    def request(_):
        start.wait()
        return model_tools.get_model()

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(request, range(6)))
    assert all(result is sentinel for result in results)
    assert len(calls) == 1


def test_package_and_lifecycle_imports_do_not_load_ml_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import context_broker; from context_broker import lifecycle; import sys; "
                "assert 'torch' not in sys.modules; assert 'sentence_transformers' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_chunked_scores_match_cosine_reference():
    import numpy as np
    from context_broker.indexer_ttc.tasks.search_tasks import similarity_scores

    rng = np.random.default_rng(12)
    vectors = rng.normal(size=(2050, 64)).astype(np.float32)
    vectors[50] = 0
    query = rng.normal(size=(1, 64)).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
    expected = np.divide(vectors @ query[0], norms, out=np.zeros(2050), where=norms != 0)
    np.testing.assert_allclose(similarity_scores(query, vectors), expected, atol=1e-6)
    assert not similarity_scores(np.zeros(64), vectors).any()


def test_index_refresh_and_concurrent_reuse(tmp_path, monkeypatch):
    import numpy as np
    from context_broker.indexer_ttc.tasks import index_tasks
    from context_broker.indexer_ttc.tools import index_cache_tools

    state.INDEXES.clear()
    calls = []

    class Model:
        def encode(self, documents, **kwargs):
            calls.append(list(documents))
            return np.ones((len(documents), 3), dtype=np.float32)

    class Encoder:
        def encode(self, text):
            return text.split()

    monkeypatch.setattr(index_tasks, "get_model", lambda: Model())
    monkeypatch.setattr(index_tasks, "get_encoder", lambda: Encoder())
    root = tmp_path / "project"
    root.mkdir()
    source = root / "first.py"
    source.write_text("x = 1\n")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with ThreadPoolExecutor(max_workers=6) as executor:
        indexes = list(executor.map(index_tasks.get_index_for_project, [str(root), str(alias)] * 3))
    assert all(idx is indexes[0] for idx in indexes)
    assert len(calls) == 1
    assert "model" not in indexes[0] and "encoder" not in indexes[0]
    old = indexes[0]["fingerprint"]
    source.write_text("x = 2\n")
    assert index_tasks.get_index_for_project(str(root))["fingerprint"] != old
    added = root / "second.py"
    added.write_text("y = 3\n")
    assert len(index_tasks.get_index_for_project(str(root))["paths"]) == 2
    source.unlink()
    assert index_tasks.get_index_for_project(str(root))["paths"] == [str(added)]
    state.INDEXES.clear()
    loaded = index_tasks.get_index_for_project(str(root))
    assert isinstance(loaded["embeddings"], np.memmap)
    assert loaded["from_disk"]
    assert len(calls) == 4
    index_tasks.clear_index(str(root))
    assert index_cache_tools.load_index_cache(str(root), current_paths=[str(added)]) is None
