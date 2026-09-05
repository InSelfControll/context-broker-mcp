"""
Cache helpers for semantic search queries.

The query cache is persisted as local JSON only — no external services
(no Redis, no pub/sub, no queues).
"""

import hashlib
import json
import os
from typing import Any

from context_broker.config import QUERY_CACHE_MAX_ENTRIES, QUERY_CACHE_MAX_FILE_BYTES
from context_broker.indexer_ttc.tools import state
from context_broker.storage_ttc.tools.json_tools import atomic_write_json
from context_broker.utils import get_cache_path, log


def generate_cache_key(query: str, top_k: int) -> str:
    """Generate stable cache key from query and parameters."""
    key_str = f"{query}:{top_k}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def load_query_cache(project_root: str) -> dict[str, Any]:
    """Load only a bounded, validated, project-specific cache."""
    project_root = state.canonical_root(project_root)
    cached = state.QUERY_CACHE.get(project_root)
    if cached is not None:
        return cached
    cache_path = get_cache_path(project_root)
    entries: dict[str, Any] = {}
    try:
        if (
            QUERY_CACHE_MAX_ENTRIES > 0
            and cache_path.exists()
            and cache_path.stat().st_size <= QUERY_CACHE_MAX_FILE_BYTES
        ):
            payload = json.loads(cache_path.read_text())
            if isinstance(payload, dict):
                entries = {
                    k: v
                    for k, v in list(payload.items())[-QUERY_CACHE_MAX_ENTRIES:]
                    if isinstance(v, dict)
                }
    except (OSError, ValueError) as exc:
        log(f"⚠️ Query cache load failed: {exc}", "WARN")
    state.QUERY_CACHE[project_root] = entries
    return entries


def save_query_cache(project_root: str) -> None:
    """Persist bounded query metadata using atomic replacement."""
    project_root = state.canonical_root(project_root)
    entries = state.QUERY_CACHE.get(project_root)
    if entries is None:
        return
    while len(entries) > QUERY_CACHE_MAX_ENTRIES:
        entries.pop(next(iter(entries)))
    state.QUERY_CACHE[project_root] = entries
    if len(json.dumps(entries).encode()) > QUERY_CACHE_MAX_FILE_BYTES:
        return
    try:
        atomic_write_json(get_cache_path(project_root), entries, pretty=False)
    except OSError as exc:
        log(f"⚠️ Query cache save failed: {exc}", "WARN")


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
