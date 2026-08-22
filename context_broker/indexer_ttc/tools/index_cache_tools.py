"""Disk persistence for semantic project indexes.

In-memory indexes are dropped after idle cleanup. Rebuilding embeddings for a
large tree is what pushes MCP ``search_context`` past client timeouts. Persisting
embeddings + path metadata under the project ``.cache/`` directory lets cold
starts reload the corpus without re-encoding every file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

from context_broker.config import EMBEDDING_MODEL, INDEX_DISK_CACHE_ENABLED
from context_broker.indexer_ttc.tools.cache_tools import (
    generate_index_fingerprint,
    get_file_mtimes,
)
from context_broker.utils import log

_INDEX_META_NAME = "context-broker-index.json"
_INDEX_VECTORS_NAME = "context-broker-index.npy"
_INDEX_CACHE_VERSION = 1


def get_index_cache_paths(project_root: str | Path) -> tuple[Path, Path]:
    """Return ``(metadata_json, embeddings_npy)`` paths under project ``.cache/``."""
    cache_dir = Path(project_root) / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / _INDEX_META_NAME, cache_dir / _INDEX_VECTORS_NAME


def build_corpus_fingerprint(paths: list[str]) -> str:
    """Fingerprint the indexed corpus from absolute path mtimes."""
    return generate_index_fingerprint(get_file_mtimes(paths))


def save_index_cache(
    project_root: str,
    *,
    paths: list[str],
    embeddings: np.ndarray,
    total_tokens: int,
    model_name: str = EMBEDDING_MODEL,
) -> bool:
    """Persist embeddings and path metadata. Returns True on success."""
    if not INDEX_DISK_CACHE_ENABLED:
        return False
    if embeddings is None or len(paths) == 0:
        return False

    meta_path, vectors_path = get_index_cache_paths(project_root)
    fingerprint = build_corpus_fingerprint(paths)
    payload = {
        "version": _INDEX_CACHE_VERSION,
        "model": model_name,
        "fingerprint": fingerprint,
        "paths": paths,
        "total_tokens": int(total_tokens),
        "embedding_shape": list(np.asarray(embeddings).shape),
        "embedding_dtype": str(np.asarray(embeddings).dtype),
    }
    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    # np.save appends ".npy" unless the path already ends with it — keep the
    # temp name *.tmp.npy so the write lands on the path we replace from.
    tmp_vectors = vectors_path.with_name(vectors_path.name + ".tmp")
    if not str(tmp_vectors).endswith(".npy"):
        tmp_vectors = Path(str(tmp_vectors) + ".npy")
    try:
        with open(tmp_vectors, "wb") as handle:
            np.save(handle, np.asarray(embeddings), allow_pickle=False)
        with open(tmp_meta, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(tmp_vectors, vectors_path)
        os.replace(tmp_meta, meta_path)
        log(f"💾 Saved index cache ({len(paths)} files) → {meta_path}")
        return True
    except Exception as exc:
        log(f"⚠ Index cache save failed: {exc}", "WARN")
        for path in (tmp_meta, tmp_vectors):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def load_index_cache(
    project_root: str,
    *,
    current_paths: list[str],
    model_name: str = EMBEDDING_MODEL,
) -> Optional[dict[str, Any]]:
    """Load a valid disk index matching *current_paths* and *model_name*.

    Returns dict with ``paths``, ``embeddings``, ``total_tokens``, ``fingerprint``
    or None when missing/stale/corrupt.
    """
    if not INDEX_DISK_CACHE_ENABLED:
        return None

    meta_path, vectors_path = get_index_cache_paths(project_root)
    if not meta_path.is_file() or not vectors_path.is_file():
        return None

    try:
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
    except Exception as exc:
        log(f"⚠ Index cache meta load failed: {exc}", "WARN")
        return None

    if int(meta.get("version", 0)) != _INDEX_CACHE_VERSION:
        log("⚠ Index cache version mismatch; rebuilding", "WARN")
        return None
    if meta.get("model") != model_name:
        log(
            f"⚠ Index cache model mismatch "
            f"(cached={meta.get('model')!r}, want={model_name!r}); rebuilding",
            "WARN",
        )
        return None

    cached_paths = meta.get("paths") or []
    if not isinstance(cached_paths, list) or not cached_paths:
        return None
    if list(cached_paths) != list(current_paths):
        log("🔄 Index cache path set changed; rebuilding")
        return None

    expected_fp = build_corpus_fingerprint(current_paths)
    if meta.get("fingerprint") != expected_fp:
        log("🔄 Index cache fingerprint stale; rebuilding")
        return None

    try:
        embeddings = np.load(vectors_path, allow_pickle=False)
    except Exception as exc:
        log(f"⚠ Index cache vectors load failed: {exc}", "WARN")
        return None

    expected_shape = meta.get("embedding_shape")
    if expected_shape is not None and list(embeddings.shape) != list(expected_shape):
        log("⚠ Index cache embedding shape mismatch; rebuilding", "WARN")
        return None
    if embeddings.shape[0] != len(current_paths):
        log("⚠ Index cache row count mismatch; rebuilding", "WARN")
        return None

    log(f"⚡ Loaded index cache ({len(current_paths)} files) from disk")
    return {
        "paths": list(cached_paths),
        "embeddings": embeddings,
        "total_tokens": int(meta.get("total_tokens", 0)),
        "fingerprint": expected_fp,
        "from_disk": True,
    }


def clear_index_cache(project_root: str) -> bool:
    """Delete on-disk index cache files for *project_root*."""
    meta_path, vectors_path = get_index_cache_paths(project_root)
    removed = False
    for path in (meta_path, vectors_path):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError as exc:
            log(f"⚠ Failed to remove index cache {path}: {exc}", "WARN")
    return removed
