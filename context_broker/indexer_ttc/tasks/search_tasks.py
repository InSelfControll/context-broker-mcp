"""
Search execution tasks.
"""

import os
from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from context_broker.config import RESULT_FILE_MAX_CHARS
from context_broker.indexer_ttc.tasks.index_tasks import (
    ProgressCallback,
    _emit,
    get_index_for_project,
)
from context_broker.indexer_ttc.tasks.snippet_tasks import (
    extract_query_terms,
    prepare_result_content,
)
from context_broker.indexer_ttc.tools import state
from context_broker.indexer_ttc.tools.cache_tools import (
    generate_cache_key,
    generate_index_fingerprint,
    get_file_mtimes,
    is_cache_valid,
    load_query_cache,
    save_query_cache,
)
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.indexer_ttc.tools.token_report_tools import persist_token_report
from context_broker.project import get_project_name
from context_broker.utils import log, log_ascii_table


def _token_savings_vs_corpus(total_tokens: int, context_tokens: int) -> tuple[int, float]:
    """Corpus baseline minus reply tokens; clamp so savings are never negative."""
    if total_tokens <= 0:
        return 0, 0.0
    saved = total_tokens - context_tokens
    if saved < 0:
        saved = 0
    return saved, (saved / total_tokens) * 100.0


def search_codebase(
    query: str,
    project_root: str,
    top_k: int = 5,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Search the codebase using semantic similarity."""
    if not project_root:
        raise ValueError("project_root is required")

    project_root = os.path.abspath(project_root)
    cache_key = generate_cache_key(query, top_k)
    cache = load_query_cache(project_root)

    idx = get_index_for_project(project_root, progress_callback=progress_callback)
    if idx is None:
        raise ValueError(f"No files found in {project_root}")

    current_mtimes = get_file_mtimes(idx["paths"])
    if cache_key in cache:
        cache_entry = cache[cache_key]
        if is_cache_valid(cache_entry, current_mtimes):
            log(f"⚡ CACHE HIT for query: {query[:50]}...")
            _emit(progress_callback, "⚡ Query cache hit — reusing previous results")
            return _load_cached_results(cache_entry, idx)
        log(f"🔄 Cache STALE for query: {query[:50]}...")

    log(f"🔍 CACHE MISS for query: {query[:50]}...")
    _emit(progress_callback, f"🧮 Scoring {len(idx['paths'])} indexed documents...")
    query_vec = idx["model"].encode([query])
    scores = cosine_similarity(query_vec, idx["embeddings"])[0]
    top_indices = np.argsort(scores)[::-1][:top_k]

    results: list[dict[str, Any]] = []
    result_paths: list[str] = []
    context_tokens = 0
    encoder = idx["encoder"]
    query_terms = extract_query_terms(query)
    truncated_files = 0

    for i in top_indices:
        path = idx["paths"][i]
        raw_content = read_file_content(path, max_chars=RESULT_FILE_MAX_CHARS)
        if not raw_content:
            continue
        snippet_text, snippet_tokens, was_truncated = prepare_result_content(
            raw_content, query_terms, encoder
        )
        if not snippet_text or snippet_tokens <= 0:
            continue
        result_paths.append(path)
        context_tokens += snippet_tokens
        if was_truncated:
            truncated_files += 1
        results.append(
            {
                "path": path,
                "content": snippet_text,
                "similarity_score": float(scores[i]),
                "tokens": snippet_tokens,
                "truncated": was_truncated,
            }
        )

    cache[cache_key] = {
        "query": query,
        "top_k": top_k,
        "result_paths": result_paths,
        "file_mtimes": get_file_mtimes(result_paths),
        "index_fingerprint": generate_index_fingerprint(current_mtimes),
    }
    state.QUERY_CACHE[project_root] = cache
    save_query_cache(project_root)

    total_tokens = idx["total_tokens"]
    saved_tokens, saved_percent = _token_savings_vs_corpus(total_tokens, context_tokens)
    project_name = get_project_name(project_root)
    report = {
        "query": query,
        "project": project_name,
        "project_root": project_root,
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "returned_files": len(results),
        "truncated_files": truncated_files,
        "total_files": len(idx["paths"]),
        "from_cache": False,
    }
    state.LAST_TOKEN_REPORTS[project_root] = report
    persist_token_report(project_root, report)
    log_ascii_table(project_name, total_tokens, context_tokens, saved_tokens, saved_percent)

    return {
        "query": query,
        "project": project_name,
        "project_root": project_root,
        "results": results,
        "total_files": len(idx["paths"]),
        "returned_files": len(results),
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "truncated_files": truncated_files,
        "from_cache": False,
    }


def _load_cached_results(cache_entry: dict[str, Any], idx: dict[str, Any]) -> dict[str, Any]:
    """Load cached results by re-reading file snippets."""
    cached_paths = cache_entry.get("result_paths", [])
    query = cache_entry.get("query", "")
    query_terms = extract_query_terms(query)
    results: list[dict[str, Any]] = []
    context_tokens = 0
    encoder = idx["encoder"]
    truncated_files = 0

    for path in cached_paths:
        raw_content = read_file_content(path, max_chars=RESULT_FILE_MAX_CHARS)
        if not raw_content:
            continue
        snippet_text, snippet_tokens, was_truncated = prepare_result_content(
            raw_content, query_terms, encoder
        )
        if not snippet_text or snippet_tokens <= 0:
            continue
        context_tokens += snippet_tokens
        if was_truncated:
            truncated_files += 1
        results.append(
            {
                "path": path,
                "content": snippet_text,
                "similarity_score": 0.0,
                "tokens": snippet_tokens,
                "truncated": was_truncated,
            }
        )

    total_tokens = idx["total_tokens"]
    saved_tokens, saved_percent = _token_savings_vs_corpus(total_tokens, context_tokens)
    project_name = get_project_name(idx["project_root"])
    report = {
        "query": query,
        "project": project_name,
        "project_root": idx["project_root"],
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "returned_files": len(results),
        "truncated_files": truncated_files,
        "total_files": len(idx["paths"]),
        "from_cache": True,
    }
    state.LAST_TOKEN_REPORTS[idx["project_root"]] = report
    persist_token_report(idx["project_root"], report)
    log_ascii_table(project_name, total_tokens, context_tokens, saved_tokens, saved_percent)

    return {
        "query": report["query"],
        "project": project_name,
        "project_root": idx["project_root"],
        "results": results,
        "total_files": len(idx["paths"]),
        "returned_files": len(results),
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "truncated_files": truncated_files,
        "from_cache": True,
    }
