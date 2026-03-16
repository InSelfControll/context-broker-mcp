"""
Shared in-memory state for indexer modules.
"""

from typing import Any, Optional

import tiktoken
from sentence_transformers import SentenceTransformer

INDEXES: dict[str, dict[str, Any]] = {}
QUERY_CACHE: dict[str, dict[str, Any]] = {}
LAST_TOKEN_REPORTS: dict[str, dict[str, Any]] = {}
LAST_PERSISTED_TOKEN_REPORT_HASHES: dict[str, str] = {}

SHARED_MODEL: Optional[SentenceTransformer] = None
ENCODER: Optional[tiktoken.Encoding] = None
