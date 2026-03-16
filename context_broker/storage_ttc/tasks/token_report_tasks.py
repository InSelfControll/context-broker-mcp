"""
Token counter report persistence tasks.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from context_broker.config import TOKEN_COUNTER_FILENAME, TOKEN_COUNTER_SUBDIR
from context_broker.storage_ttc.tasks.json_tasks import load_json_data, save_json_data


def save_token_counter_report(project_name: str, project_root: str, report: dict[str, Any]) -> str:
    """Persist latest token counter report as internal JSON."""
    payload = {
        "type": "token-counter-report",
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
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


def load_token_counter_report(project_name: str, project_root: str = "") -> Optional[dict[str, Any]]:
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
