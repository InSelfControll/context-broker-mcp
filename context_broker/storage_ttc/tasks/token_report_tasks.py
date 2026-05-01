"""
Token counter report persistence tasks.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from context_broker.config import (
    TOKEN_COUNTER_FILENAME,
    TOKEN_COUNTER_RUNS_SUBDIR,
    TOKEN_COUNTER_SUBDIR,
)
from context_broker.storage_ttc.tasks.json_tasks import (
    list_saved_json,
    load_json_data,
    save_json_data,
)


def _token_run_filename(report: dict[str, Any], updated_at: str) -> str:
    """Create a stable, unique filename for one token report run."""
    digest = hashlib.sha256(
        json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    safe_timestamp = updated_at.replace(":", "-").replace("+", "Z")
    return f"token-run-{safe_timestamp}-{digest}-{uuid4().hex[:8]}.json"


def save_token_counter_report(project_name: str, project_root: str, report: dict[str, Any]) -> str:
    """Persist latest token counter report as internal JSON."""
    updated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "type": "token-counter-report",
        "version": 1,
        "updated_at": updated_at,
        "project": project_name,
        "project_root": project_root,
        "report": report,
    }
    return save_json_data(
        project_name=project_name,
        filename=TOKEN_COUNTER_FILENAME,
        data=payload,
        subdir=TOKEN_COUNTER_SUBDIR,
        project_root=project_root,
        pretty=True,
    )


def save_token_counter_run(project_name: str, project_root: str, report: dict[str, Any]) -> str:
    """Persist one immutable token counter report for history/graph views."""
    updated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "type": "token-counter-run",
        "version": 1,
        "updated_at": updated_at,
        "project": project_name,
        "project_root": project_root,
        "report": report,
    }
    return save_json_data(
        project_name=project_name,
        filename=_token_run_filename(report, updated_at),
        data=payload,
        subdir=TOKEN_COUNTER_RUNS_SUBDIR,
        project_root=project_root,
        pretty=True,
    )


def load_token_counter_report(
    project_name: str, project_root: str = ""
) -> Optional[dict[str, Any]]:
    """Load latest persisted token counter report."""
    data = load_json_data(
        project_name=project_name,
        filename=TOKEN_COUNTER_FILENAME,
        subdir=TOKEN_COUNTER_SUBDIR,
        project_root=project_root,
    )
    if not isinstance(data, dict):
        return None
    report = data.get("report")
    return report if isinstance(report, dict) else None


def list_token_counter_runs(
    project_name: str, project_root: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Load recent token counter run payloads, newest first."""
    filenames = list_saved_json(
        project_name=project_name,
        subdir=TOKEN_COUNTER_RUNS_SUBDIR,
        project_root=project_root,
    )
    runs: list[dict[str, Any]] = []
    for filename in filenames:
        data = load_json_data(
            project_name=project_name,
            filename=filename,
            subdir=TOKEN_COUNTER_RUNS_SUBDIR,
            project_root=project_root,
        )
        if not isinstance(data, dict) or data.get("type") != "token-counter-run":
            continue
        data["filename"] = filename
        runs.append(data)

    runs.sort(key=lambda run: str(run.get("updated_at", "")), reverse=True)
    return runs[: max(0, limit)]
