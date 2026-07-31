"""
Index building and lifecycle tasks.
"""

import os
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
    clear_index_cache,
    load_index_cache,
    save_index_cache,
)
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.indexer_ttc.tools.model_tools import get_encoder, get_model
from context_broker.project import load_ignore_patterns
from context_broker.utils import count_tokens, log


def get_index_for_project(root_path: str) -> Optional[dict[str, Any]]:
    """Get or create semantic index for project files."""
    root_path = os.path.abspath(root_path)
    if root_path in state.INDEXES:
        return state.INDEXES[root_path]

    log(f"⚡ Indexing new project: {root_path}")
    model = get_model()
    encoder = get_encoder()
    ignore_patterns = load_ignore_patterns(root_path)
    # Same per-file byte budget as search snippets so corpus token totals match the "full slice" baseline.
    read_cap = max(INDEX_FILE_MAX_CHARS, RESULT_FILE_MAX_CHARS)

    file_paths = collect_project_files(
        root_path,
        ignore_dirs=DEFAULT_IGNORE_DIRS,
        ignore_patterns=ignore_patterns,
    )
    if not file_paths:
        log("⚠️ No files found to index", "WARN")
        return None

    cached = load_index_cache(
        root_path,
        current_paths=file_paths,
        model_name=EMBEDDING_MODEL,
    )
    if cached is not None:
        index_data = {
            "embeddings": cached["embeddings"],
            "paths": cached["paths"],
            "model": model,
            "encoder": encoder,
            "total_tokens": cached["total_tokens"],
            "ignore_patterns": ignore_patterns,
            "project_root": root_path,
            "from_disk": True,
        }
        state.INDEXES[root_path] = index_data
        log(
            f"✅ Index ready (disk cache). Total size: "
            f"{cached['total_tokens']:,} tokens across {len(cached['paths'])} files."
        )
        return index_data

    documents: list[str] = []
    paths: list[str] = []
    total_project_tokens = 0

    for file_path in file_paths:
        content = read_file_content(file_path, max_chars=read_cap)
        if content is None:
            continue
        total_project_tokens += count_tokens(content, encoder)
        documents.append(f"File: {file_path}\nContent: {content[:3000]}")
        paths.append(file_path)

    if not documents:
        log("⚠️ No files found to index", "WARN")
        return None

    log(f"🧠 Embedding {len(documents)} files...")
    embeddings = np.asarray(
        model.encode(documents, batch_size=BATCH_SIZE, show_progress_bar=False)
    )
    save_index_cache(
        root_path,
        paths=paths,
        embeddings=embeddings,
        total_tokens=total_project_tokens,
        model_name=EMBEDDING_MODEL,
    )
    index_data = {
        "embeddings": embeddings,
        "paths": paths,
        "model": model,
        "encoder": encoder,
        "total_tokens": total_project_tokens,
        "ignore_patterns": ignore_patterns,
        "project_root": root_path,
        "from_disk": False,
    }
    state.INDEXES[root_path] = index_data
    log(
        f"✅ Index ready. Total size: {total_project_tokens:,} tokens across {len(documents)} files."
    )
    return index_data


def clear_index(project_root: str) -> bool:
    """Clear in-memory index, on-disk embedding cache, and token-report state."""
    root_path = os.path.abspath(project_root)
    state.LAST_TOKEN_REPORTS.pop(root_path, None)
    state.LAST_PERSISTED_TOKEN_REPORT_HASHES.pop(root_path, None)
    disk_cleared = clear_index_cache(root_path)
    if root_path in state.INDEXES:
        del state.INDEXES[root_path]
        log(f"🗑️ Cleared index for: {root_path}")
        return True
    return disk_cleared
