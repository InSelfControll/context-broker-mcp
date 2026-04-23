"""Public API surface for documentation management tasks."""

from context_broker.docs_ttc.tasks.docs_tasks import ensure_docs, docs_stats, scan_docs

__all__ = ["ensure_docs", "scan_docs", "docs_stats"]
