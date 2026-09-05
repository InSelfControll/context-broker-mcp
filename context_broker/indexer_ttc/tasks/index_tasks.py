"""
Index building and lifecycle tasks.
"""

from typing import Any, Optional

import numpy as np

from context_broker.config import (
    BATCH_SIZE,
    DEFAULT_IGNORE_DIRS,
    EMBEDDING_MODEL,
    INDEX_FILE_MAX_CHARS,
    RESULT_FILE_MAX_CHARS,
)
from context_broker.indexer_ttc.tools import state
from context_broker.indexer_ttc.tools.collect_tools import collect_project_files
from context_broker.indexer_ttc.tools.index_cache_tools import (
    build_corpus_fingerprint,
    clear_index_cache,
    load_index_cache,
    save_index_cache,
)
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.indexer_ttc.tools.model_tools import get_encoder, get_model
from context_broker.project import load_ignore_patterns
from context_broker.utils import count_tokens, log


def get_index_for_project(root_path: str) -> Optional[dict[str, Any]]:
    """Reuse one validated project index across all sessions in this process."""
    root_path = state.canonical_root(root_path)
    with state.project_lock(root_path):
        return _get_index_locked(root_path)


def _get_index_locked(root_path: str) -> Optional[dict[str, Any]]:
    ignore_patterns = load_ignore_patterns(root_path)
    file_paths = collect_project_files(
        root_path,
        ignore_dirs=DEFAULT_IGNORE_DIRS,
        ignore_patterns=ignore_patterns,
    )
    fingerprint = build_corpus_fingerprint(file_paths)
    existing = state.INDEXES.get(root_path)
    if existing is not None and existing.get("fingerprint") == fingerprint:
        return existing
    state.INDEXES.pop(root_path, None)
    if not file_paths:
        return None

    cached = load_index_cache(root_path, current_paths=file_paths, model_name=EMBEDDING_MODEL)
    if cached is not None:
        index_data = dict(cached, ignore_patterns=ignore_patterns, project_root=root_path)
        state.INDEXES[root_path] = index_data
        return index_data

    encoder = get_encoder()
    read_cap = max(INDEX_FILE_MAX_CHARS, RESULT_FILE_MAX_CHARS)
    paths: list[str] = []
    total_tokens = 0
    embeddings = None
    documents: list[str] = []
    batch_size = max(1, BATCH_SIZE)
    row = 0

    def encode_batch() -> None:
        nonlocal embeddings, row
        if not documents:
            return
        with state.INFERENCE_LOCK:
            batch = np.asarray(
                get_model().encode(
                    documents,
                    batch_size=batch_size,
                    show_progress_bar=False,
                ),
                dtype=np.float32,
            )
        if embeddings is None:
            embeddings = np.empty((len(file_paths), batch.shape[1]), dtype=np.float32)
        embeddings[row : row + len(batch)] = batch
        row += len(batch)
        documents.clear()

    for file_path in file_paths:
        content = read_file_content(file_path, max_chars=read_cap)
        if content is None:
            continue
        total_tokens += count_tokens(content, encoder)
        documents.append(f"File: {file_path}\nContent: {content[:3000]}")
        paths.append(file_path)
        if len(documents) >= batch_size:
            encode_batch()
    encode_batch()
    if embeddings is None:
        return None
    embeddings = embeddings[:row]
    if row < len(file_paths):
        embeddings = embeddings.copy()
    # Do not mark a build as fresh if files changed while they were being read.
    if build_corpus_fingerprint(file_paths) != fingerprint:
        raise RuntimeError("project changed during indexing; retry the search")
    save_index_cache(
        root_path,
        paths=paths,
        embeddings=embeddings,
        total_tokens=total_tokens,
        model_name=EMBEDDING_MODEL,
        source_paths=file_paths,
        source_fingerprint=fingerprint,
    )
    index_data = {
        "embeddings": embeddings,
        "paths": paths,
        "total_tokens": total_tokens,
        "fingerprint": fingerprint,
        "ignore_patterns": ignore_patterns,
        "project_root": root_path,
        "from_disk": False,
    }
    state.INDEXES[root_path] = index_data
    log(f"✅ Index ready: {len(paths)} files, {total_tokens:,} tokens")
    return index_data


def clear_index(project_root: str) -> bool:
    """Clear in-memory index, on-disk embedding cache, and token-report state."""
    root_path = state.canonical_root(project_root)
    with state.project_lock(root_path):
        return _clear_index_locked(root_path)


def _clear_index_locked(root_path: str) -> bool:
    state.QUERY_CACHE.pop(root_path, None)
    state.LAST_TOKEN_REPORTS.pop(root_path, None)
    state.LAST_PERSISTED_TOKEN_REPORT_HASHES.pop(root_path, None)
    disk_cleared = clear_index_cache(root_path)
    if state.INDEXES.pop(root_path, None) is not None:
        log(f"🗑️ Cleared index for: {root_path}")
        return True
    return disk_cleared
