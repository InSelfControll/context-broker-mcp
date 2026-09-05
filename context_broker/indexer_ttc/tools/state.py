"""
Shared in-memory state for indexer modules.
"""

import hashlib
import os
from threading import RLock
from typing import Any

from context_broker.config import MEMORY_POOL_BYTES
from context_broker.indexer_ttc.tools.memory_pool import MemoryPool

POOL = MemoryPool(MEMORY_POOL_BYTES)
INDEXES = POOL.namespace("indexes")
QUERY_CACHE = POOL.namespace("queries")
LAST_TOKEN_REPORTS = POOL.namespace("reports")
LAST_PERSISTED_TOKEN_REPORT_HASHES = POOL.namespace("report-hashes")
SHARED_MODEL: Any = None
ENCODER: Any = None
MODEL_LOCK = RLock()
INFERENCE_LOCK = RLock()
_PROJECT_LOCKS = tuple(RLock() for _ in range(64))


def canonical_root(project_root: str) -> str:
    """Use one cache identity for relative paths and symlinks to the same project."""
    return os.path.realpath(project_root)


def project_lock(project_root: str) -> RLock:
    """Bound lock allocation while serializing work for each project."""
    digest = hashlib.sha256(canonical_root(project_root).encode()).digest()
    return _PROJECT_LOCKS[int.from_bytes(digest[:4]) % len(_PROJECT_LOCKS)]
