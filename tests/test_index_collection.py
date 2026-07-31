"""Tests for safe file collection and on-disk embedding index cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from context_broker.indexer_ttc.tools.collect_tools import collect_project_files
from context_broker.indexer_ttc.tools import index_cache_tools
from context_broker.indexer_ttc.tasks import index_tasks
from context_broker.indexer_ttc.tools import state


def _patch_ignore_dirs(monkeypatch) -> None:
    """Allow pytest tmp_path projects (under /tmp) to be walked."""
    from context_broker.config import DEFAULT_IGNORE_DIRS

    cleaned = DEFAULT_IGNORE_DIRS - {"tmp", "temp"}
    monkeypatch.setattr(
        "context_broker.indexer_ttc.tools.collect_tools.DEFAULT_IGNORE_DIRS",
        cleaned,
    )
    monkeypatch.setattr(index_tasks, "DEFAULT_IGNORE_DIRS", cleaned)


def test_collect_skips_directory_symlinks(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")

    # External tree lives *outside* the project root so the only way in is the
    # directory symlink (the classic Nix `result` → /nix/store case).
    external = tmp_path / "external_store"
    external.mkdir()
    (external / "secret.py").write_text("x = 1\n", encoding="utf-8")
    nested = external
    for i in range(5):
        nested = nested / f"layer{i}"
        nested.mkdir()
        (nested / f"blob{i}.py").write_text(f"x={i}\n", encoding="utf-8")

    (project / "result").symlink_to(external, target_is_directory=True)

    files = collect_project_files(str(project), follow_symlinks=False)
    basenames = {Path(p).name for p in files}
    assert "app.py" in basenames
    assert "secret.py" not in basenames
    assert not any("external_store" in p for p in files)
    assert not any(Path(p).name.startswith("blob") for p in files)


def test_collect_prunes_result_dir_even_if_real(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
    result = tmp_path / "result"
    result.mkdir()
    (result / "generated.py").write_text("y=2\n", encoding="utf-8")

    files = collect_project_files(str(tmp_path))
    assert any(p.endswith("main.py") for p in files)
    assert not any("generated.py" in p for p in files)


def test_collect_skips_oversized_files(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    (tmp_path / "small.py").write_text("a=1\n", encoding="utf-8")
    big = tmp_path / "big.py"
    big.write_bytes(b"x" * 5000)

    files = collect_project_files(str(tmp_path), max_file_bytes=100)
    assert any(p.endswith("small.py") for p in files)
    assert not any(p.endswith("big.py") for p in files)


def test_collect_skips_iso_and_archive_files(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
    # Even if someone later adds these to SUPPORTED_EXTENSIONS, hard-ignore wins.
    (tmp_path / "ofir-nixos-kde-installer.iso").write_bytes(b"ISO")
    (tmp_path / "Installer.ISO").write_bytes(b"ISO")
    (tmp_path / "disk.qcow2").write_bytes(b"QCOW")
    (tmp_path / "bundle.tar.gz").write_bytes(b"TGZ")
    (tmp_path / "notes.md").write_text("# hi\n", encoding="utf-8")

    files = collect_project_files(
        str(tmp_path),
        extensions=["*.py", "*.md", "*.iso", "*.qcow2", "*.gz"],
    )
    basenames = {Path(p).name for p in files}
    assert "main.py" in basenames
    assert "notes.md" in basenames
    assert "ofir-nixos-kde-installer.iso" not in basenames
    assert "Installer.ISO" not in basenames
    assert "disk.qcow2" not in basenames
    assert "bundle.tar.gz" not in basenames


def test_should_ignore_blocks_iso_case_insensitive() -> None:
    from context_broker.project_ttc.tasks.ignore_tasks import should_ignore

    assert should_ignore(
        "/p/ofir-nixos-kde-installer.iso",
        "ofir-nixos-kde-installer.iso",
        [],
        set(),
    )
    assert should_ignore("/p/Installer.ISO", "Installer.ISO", [], set())
    assert should_ignore("/p/vm.qcow2", "images/vm.qcow2", [], set())
    assert not should_ignore("/p/main.py", "main.py", [], set())


def test_index_disk_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    monkeypatch.setattr(index_cache_tools, "INDEX_DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(index_cache_tools, "EMBEDDING_MODEL", "test-model")

    paths = [str(tmp_path / "a.py"), str(tmp_path / "b.py")]
    for path in paths:
        Path(path).write_text("print(1)\n", encoding="utf-8")
    vectors = np.asarray([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)

    assert index_cache_tools.save_index_cache(
        str(tmp_path),
        paths=paths,
        embeddings=vectors,
        total_tokens=12,
        model_name="test-model",
    )

    loaded = index_cache_tools.load_index_cache(
        str(tmp_path),
        current_paths=paths,
        model_name="test-model",
    )
    assert loaded is not None
    assert loaded["total_tokens"] == 12
    assert loaded["paths"] == paths
    assert np.allclose(loaded["embeddings"], vectors)

    # Touch a file → fingerprint changes → cache miss
    Path(paths[0]).write_text("print(2)\n", encoding="utf-8")
    stale = index_cache_tools.load_index_cache(
        str(tmp_path),
        current_paths=paths,
        model_name="test-model",
    )
    assert stale is None


def test_get_index_uses_disk_cache_without_reencode(tmp_path: Path, monkeypatch) -> None:
    _patch_ignore_dirs(monkeypatch)
    monkeypatch.setattr(index_cache_tools, "INDEX_DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(index_cache_tools, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(index_tasks, "EMBEDDING_MODEL", "test-model")

    (tmp_path / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    paths = [str(tmp_path / "mod.py")]
    vectors = np.asarray([[0.5, 0.25, 0.125]], dtype=np.float32)
    assert index_cache_tools.save_index_cache(
        str(tmp_path),
        paths=paths,
        embeddings=vectors,
        total_tokens=7,
        model_name="test-model",
    )

    class _FakeModel:
        def encode(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("encode should not be called when disk cache hits")

    class _FakeEncoder:
        def encode(self, text: str):
            return [1, 2, 3]

    state.INDEXES.clear()
    monkeypatch.setattr(index_tasks, "get_model", lambda: _FakeModel())
    monkeypatch.setattr(index_tasks, "get_encoder", lambda: _FakeEncoder())

    idx = index_tasks.get_index_for_project(str(tmp_path))
    assert idx is not None
    assert idx.get("from_disk") is True
    assert idx["total_tokens"] == 7
    assert np.allclose(idx["embeddings"], vectors)

    # Second call hits in-memory cache
    idx2 = index_tasks.get_index_for_project(str(tmp_path))
    assert idx2 is idx

    state.INDEXES.clear()
