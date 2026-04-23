"""Compatibility wrapper for documentation management API."""

from context_broker.docs_ttc.codebase.api import docs_stats, ensure_docs, scan_docs

__all__ = ["ensure_docs", "scan_docs", "docs_stats"]
