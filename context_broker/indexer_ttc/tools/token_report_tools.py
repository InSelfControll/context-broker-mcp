"""
Token report persistence and retrieval helpers.
"""

import hashlib
import json
import os
from typing import Any, Optional

from context_broker.config import (
    EMBEDDING_MODEL,
    ENCODING_MODEL,
    INDEX_FILE_MAX_CHARS,
    MODEL_DEVICE,
    RESULT_FILE_MAX_CHARS,
)
from context_broker.indexer_ttc.tools import state
from context_broker.project import get_project_name
from context_broker.storage import (
    load_token_counter_report,
    save_token_counter_report,
    save_token_counter_run,
)
from context_broker.utils import log


def get_last_token_report(project_root: str) -> Optional[dict[str, Any]]:
    """Get latest token usage report for a project."""
    root_path = os.path.abspath(project_root)
    in_memory = state.LAST_TOKEN_REPORTS.get(root_path)
    if in_memory is not None:
        return in_memory

    project_name = get_project_name(root_path)
    persisted = load_token_counter_report(project_name, root_path)
    if persisted is not None:
        state.LAST_TOKEN_REPORTS[root_path] = persisted
        try:
            state.LAST_PERSISTED_TOKEN_REPORT_HASHES[root_path] = hashlib.sha256(
                json.dumps(persisted, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        except Exception:
            pass
    return persisted


def enrich_token_report(report: dict[str, Any]) -> dict[str, Any]:
    """Attach stable metadata consumers need for dashboards and integrations."""
    enriched = dict(report)
    enriched.setdefault("embedding_model", EMBEDDING_MODEL)
    enriched.setdefault("encoding_model", ENCODING_MODEL)
    enriched.setdefault("model_device", MODEL_DEVICE)
    enriched.setdefault("index_file_max_chars", INDEX_FILE_MAX_CHARS)
    enriched.setdefault("result_file_max_chars", RESULT_FILE_MAX_CHARS)
    enriched.setdefault("token_baseline", "indexed-corpus-per-file-cap")
    return enriched


def persist_token_report(project_root: str, report: dict[str, Any]) -> None:
    """Persist latest token report and one immutable per-run history report."""
    root_path = os.path.abspath(project_root)
    enriched_report = enrich_token_report(report)
    report_hash = ""
    try:
        report_hash = hashlib.sha256(
            json.dumps(enriched_report, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    except Exception:
        pass

    state.LAST_TOKEN_REPORTS[root_path] = enriched_report
    # Deduplicate BEFORE creating an immutable run file, so identical repeated
    # searches do not accumulate token-history files on disk.
    if report_hash and state.LAST_PERSISTED_TOKEN_REPORT_HASHES.get(root_path) == report_hash:
        return

    try:
        project_name = get_project_name(root_path)
        save_token_counter_run(project_name, root_path, enriched_report)
        save_token_counter_report(project_name, root_path, enriched_report)
        if report_hash:
            state.LAST_PERSISTED_TOKEN_REPORT_HASHES[root_path] = report_hash
    except Exception as e:
        log(f"⚠ Failed to persist token counter report: {e}", "WARN")
