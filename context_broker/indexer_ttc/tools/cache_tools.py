"""
Cache helpers for semantic search queries.

The query cache is persisted as local JSON only — no external services
(no Redis, no pub/sub, no queues).
"""

import hashlib
import json
import os
from typing import Any

from context_broker.indexer_ttc.tools import state
from context_broker.utils import get_cache_path, log


def generate_cache_key(query: str, top_k: int) -> str:
    """Generate stable cache key from query and parameters."""
    key_str = f"{query}:{top_k}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def load_query_cache(project_root: str) -> dict[str, Any]:
    """Load query cache from disk."""
    if project_root in state.QUERY_CACHE:
        return state.QUERY_CACHE[project_root]

    cache_path = get_cache_path(project_root)
    if not cache_path.exists():
        state.QUERY_CACHE[project_root] = {}
        return {}
    try:
        with open(cache_path, "r") as f:
            state.QUERY_CACHE[project_root] = json.load(f)
            log(f"📦 Loaded cache with {len(state.QUERY_CACHE[project_root])} entries")
            return state.QUERY_CACHE[project_root]
    except Exception as e:
        log(f"⚠ Cache load failed: {e}", "WARN")
        state.QUERY_CACHE[project_root] = {}
        return {}


def save_query_cache(project_root: str) -> None:
    """Persist query cache to local JSON."""
    if project_root not in state.QUERY_CACHE:
        return

    cache_path = get_cache_path(project_root)
    try:
        with open(cache_path, "w") as f:
            json.dump(state.QUERY_CACHE[project_root], f, indent=2)
        log(f"💾 Saved cache with {len(state.QUERY_CACHE[project_root])} entries")
    except Exception as e:
        log(f"⚠ Cache save failed: {e}", "WARN")


def get_file_mtimes(paths: list[str]) -> dict[str, float]:
    """Get modification times for a list of files."""
    mtimes: dict[str, float] = {}
    for path in paths:
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            mtimes[path] = 0
    return mtimes


def generate_index_fingerprint(file_mtimes: dict[str, float]) -> str:
    """Generate a stable fingerprint for the indexed file set."""
    payload = json.dumps(file_mtimes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_cache_valid(cache_entry: dict[str, Any], current_mtimes: dict[str, float]) -> bool:
    """Validate cache entry by full-index fingerprint or legacy result mtimes."""
    index_fingerprint = cache_entry.get("index_fingerprint")
    if index_fingerprint is not None:
        return index_fingerprint == generate_index_fingerprint(current_mtimes)

    cached_mtimes = cache_entry.get("file_mtimes", {})
    for path, cached_mtime in cached_mtimes.items():
        if current_mtimes.get(path, 0) != cached_mtime:
            return False
    return True
