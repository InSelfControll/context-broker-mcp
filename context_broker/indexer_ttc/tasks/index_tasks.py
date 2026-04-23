"""
Index building and lifecycle tasks.
"""

import glob
import os
from typing import Any, Optional

from context_broker.config import (
    BATCH_SIZE,
    DEFAULT_IGNORE_DIRS,
    INDEX_FILE_MAX_CHARS,
    RESULT_FILE_MAX_CHARS,
    SUPPORTED_EXTENSIONS,
)
from context_broker.indexer_ttc.tools import state
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.indexer_ttc.tools.model_tools import get_encoder, get_model
from context_broker.project import load_ignore_patterns, should_ignore
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

    documents: list[str] = []
    paths: list[str] = []
    total_project_tokens = 0
    ignored_count = 0

    for ext in SUPPORTED_EXTENSIONS:
        pattern = os.path.join(root_path, "**", ext)
        for file_path in glob.glob(pattern, recursive=True):
            rel_path = os.path.relpath(file_path, root_path)
            if should_ignore(file_path, rel_path, ignore_patterns, DEFAULT_IGNORE_DIRS):
                ignored_count += 1
                continue
            content = read_file_content(file_path, max_chars=read_cap)
            if content is None:
                continue
            total_project_tokens += count_tokens(content, encoder)
            documents.append(f"File: {file_path}\nContent: {content[:3000]}")
            paths.append(file_path)

    if ignored_count > 0:
        log(f"🚫 Ignored {ignored_count} files based on ignore patterns")
    if not documents:
        log("⚠️ No files found to index", "WARN")
        return None

    log(f"🧠 Embedding {len(documents)} files...")
    embeddings = model.encode(documents, batch_size=BATCH_SIZE, show_progress_bar=False)
    index_data = {
        "embeddings": embeddings,
        "paths": paths,
        "model": model,
        "encoder": encoder,
        "total_tokens": total_project_tokens,
        "ignore_patterns": ignore_patterns,
        "project_root": root_path,
    }
    state.INDEXES[root_path] = index_data
    log(
        f"✅ Index ready. Total size: {total_project_tokens:,} tokens across {len(documents)} files."
    )
    return index_data


def clear_index(project_root: str) -> bool:
    """Clear in-memory index and related token-report state."""
    root_path = os.path.abspath(project_root)
    state.LAST_TOKEN_REPORTS.pop(root_path, None)
    state.LAST_PERSISTED_TOKEN_REPORT_HASHES.pop(root_path, None)
    if root_path in state.INDEXES:
        del state.INDEXES[root_path]
        log(f"🗑️ Cleared index for: {root_path}")
        return True
    return False
