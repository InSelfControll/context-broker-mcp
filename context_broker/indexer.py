"""
Compatibility wrapper for indexer API.
"""

from context_broker.indexer_ttc.codebase.api import (
    clear_index,
    get_index_for_project,
    get_last_token_report,
    literal_search,
    search_codebase,
)

__all__ = [
    "search_codebase",
    "literal_search",
    "get_index_for_project",
    "clear_index",
    "get_last_token_report",
]
