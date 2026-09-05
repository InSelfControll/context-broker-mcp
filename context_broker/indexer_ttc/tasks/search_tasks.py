"""Project-isolated semantic search with bounded allocations and shared inference."""

from typing import Any

import numpy as np

from context_broker.config import RESULT_FILE_MAX_CHARS
from context_broker.indexer_ttc.tasks.index_tasks import get_index_for_project
from context_broker.indexer_ttc.tasks.snippet_tasks import (
    extract_query_terms,
    prepare_result_content,
)
from context_broker.indexer_ttc.tools import state
from context_broker.indexer_ttc.tools.cache_tools import (
    generate_cache_key,
    load_query_cache,
    save_query_cache,
)
from context_broker.indexer_ttc.tools.io_tools import read_file_content
from context_broker.indexer_ttc.tools.model_tools import get_encoder, get_model
from context_broker.indexer_ttc.tools.token_report_tools import persist_token_report
from context_broker.project import get_project_name
from context_broker.utils import log_ascii_table


def _token_savings_vs_corpus(total_tokens: int, context_tokens: int) -> tuple[int, float]:
    if total_tokens <= 0:
        return 0, 0.0
    saved = max(0, total_tokens - context_tokens)
    return saved, saved / total_tokens * 100.0


def similarity_scores(query: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """Calculate cosine scores without normalizing/copying the whole corpus."""
    query = np.asarray(query, dtype=np.float32).reshape(-1)
    scores = np.zeros(len(embeddings), dtype=np.float32)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return scores
    for start in range(0, len(embeddings), 1024):
        block = np.asarray(embeddings[start : start + 1024], dtype=np.float32)
        norms = np.sqrt(np.einsum("ij,ij->i", block, block)) * query_norm
        np.divide(block @ query, norms, out=scores[start : start + len(block)], where=norms != 0)
    return scores


def search_codebase(query: str, project_root: str, top_k: int = 5) -> dict[str, Any]:
    """Search one canonical project using the process-wide model and cache pool."""
    if not project_root or not query.strip():
        raise ValueError("project_root and query are required")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    project_root = state.canonical_root(project_root)
    with state.project_lock(project_root):
        return _search_locked(query, project_root, top_k)


def _search_locked(query: str, project_root: str, top_k: int) -> dict[str, Any]:
    idx = get_index_for_project(project_root)
    if idx is None:
        raise ValueError(f"No files found in {project_root}")
    cache_key = generate_cache_key(query, top_k)
    cache = load_query_cache(project_root)
    cached = cache.get(cache_key)
    if (
        isinstance(cached, dict)
        and cached.get("index_fingerprint") == idx["fingerprint"]
        and isinstance(cached.get("result_paths"), list)
        and all(isinstance(p, str) for p in cached["result_paths"])
        and isinstance(cached.get("scores"), dict)
        and set(cached["result_paths"]).issubset(idx["paths"])
    ):
        cache[cache_key] = cache.pop(cache_key)
        state.QUERY_CACHE[project_root] = cache
        return _render_result(query, cached["result_paths"], cached.get("scores", {}), idx, True)

    with state.INFERENCE_LOCK:
        query_vector = get_model().encode([query])
    scores = similarity_scores(query_vector, idx["embeddings"])
    count = min(top_k, len(scores))
    indices = np.argpartition(-scores, count - 1)[:count]
    indices = indices[np.argsort(-scores[indices], kind="stable")]
    paths = [idx["paths"][i] for i in indices]
    score_map = {idx["paths"][i]: float(scores[i]) for i in indices}
    result = _render_result(query, paths, score_map, idx, False)
    cache[cache_key] = {
        "query": query,
        "top_k": top_k,
        "result_paths": paths,
        "scores": score_map,
        "index_fingerprint": idx["fingerprint"],
    }
    state.QUERY_CACHE[project_root] = cache
    save_query_cache(project_root)
    return result


def _render_result(
    query: str,
    paths: list[str],
    scores: dict[str, float],
    idx: dict[str, Any],
    cached: bool,
) -> dict[str, Any]:
    """Use the same safe snippet/report path for cache hits and fresh searches."""
    encoder = get_encoder()
    query_terms = extract_query_terms(query)
    results = []
    context_tokens = truncated_files = 0
    for path in paths:
        content = read_file_content(path, max_chars=RESULT_FILE_MAX_CHARS)
        if not content:
            continue
        snippet, tokens, truncated = prepare_result_content(content, query_terms, encoder)
        if not snippet or tokens <= 0:
            continue
        results.append(
            {
                "path": path,
                "content": snippet,
                "similarity_score": scores.get(path, 0.0),
                "tokens": tokens,
                "truncated": truncated,
            }
        )
        context_tokens += tokens
        truncated_files += int(truncated)
    total_tokens = idx["total_tokens"]
    saved_tokens, saved_percent = _token_savings_vs_corpus(total_tokens, context_tokens)
    project_root = idx["project_root"]
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
        "from_cache": cached,
    }
    persist_token_report(project_root, report)
    log_ascii_table(project_name, total_tokens, context_tokens, saved_tokens, saved_percent)
    return dict(report, results=results)
