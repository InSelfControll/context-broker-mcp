"""
Local-JSON append-only chat ledger.

Every successful save through Honcho or Redis is also mirrored to a project-
and session-scoped JSON file. This gives us:

  - **Append, never overwrite.** The on-disk file is read, the new messages
    are appended, then atomically rewritten via temp + ``os.replace``. We
    never lose prior turns.
  - **Resilience.** Chats survive even if Redis is wiped or Honcho is
    unreachable — the local ledger is the durable record.
  - **Visibility.** A human-readable JSON record per ``(project, session)``.

Layout (honoring ``CONTEXT_BROKER_STORAGE_MODE``):

  <STORAGE_BASE_DIR>/chats/<project_digest>/<session_id>.json
  <project_root>/.context-broker/chats/<project_digest>/<session_id>.json

File schema::

  {
    "project": {"digest": "...", "name": "...", "root": "..."},
    "session_id": "...",
    "messages": [
      {"peer_id": "...", "content": "...", "created_at": <float>}
    ]
  }
"""

import json
import time
from pathlib import Path
from typing import Any

from filelock import FileLock

from context_broker.config import (
    IN_PROJECT_FOLDER,
    STORAGE_BASE_DIR,
    STORAGE_MODE,
    StorageMode,
)
from context_broker.project import get_project_name
from context_broker.context_ttc.tools.identity_tools import (
    normalize_identifier as _safe_session,
    project_digest as _digest,
)
from context_broker.storage_ttc.tools.json_tools import atomic_write_json

def ledger_paths(project_root: str, session_id: str) -> list[Path]:
    """Return every ledger path that should receive the append, per STORAGE_MODE."""
    digest = _digest(project_root)
    safe = _safe_session(session_id)
    mode = STORAGE_MODE.lower()
    paths: list[Path] = []
    if mode in {StorageMode.GLOBAL, StorageMode.BOTH}:
        paths.append(Path(STORAGE_BASE_DIR) / "chats" / digest / f"{safe}.json")
    if project_root and mode in {StorageMode.IN_PROJECT, StorageMode.BOTH}:
        paths.append(
            Path(project_root) / IN_PROJECT_FOLDER / "chats" / digest / f"{safe}.json"
        )
    if not paths:  # safety net — always have one writable location
        paths.append(Path(STORAGE_BASE_DIR) / "chats" / digest / f"{safe}.json")
    return paths


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            if not isinstance(payload, dict) or not isinstance(payload.get("messages", []), list):
                raise ValueError(f"invalid chat ledger schema: {path}")
            return payload
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid chat ledger JSON: {path}") from exc


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def append_turn(
    project_root: str,
    session_id: str,
    messages: list[dict[str, Any]],
) -> list[str]:
    """Append ``messages`` to every ledger file for the (project, session).

    Returns the list of files written. Existing file contents are preserved —
    new messages are appended, never replacing prior turns.
    """
    if not messages:
        return []

    digest = _digest(project_root)
    project_meta = {
        "digest": digest,
        "name": get_project_name(project_root) if project_root else "unknown",
        "root": project_root or "",
    }
    safe_session = _safe_session(session_id)

    written: list[str] = []
    for path in ledger_paths(project_root, session_id):
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=30):
            existing = _read(path)
            existing.setdefault("project", project_meta)
            existing.setdefault("session_id", safe_session)
            existing.setdefault("messages", [])
            existing["messages"].extend(messages)
            existing["updated_at"] = time.time()
            _atomic_write(path, existing)
        written.append(str(path))
    return written


def read_ledger(project_root: str, session_id: str) -> dict[str, Any] | None:
    """Return the first existing ledger payload for (project, session), or None."""
    for path in ledger_paths(project_root, session_id):
        if path.exists():
            payload = _read(path)
            if payload:
                return payload
    return None


def list_sessions(project_root: str) -> list[str]:
    """Return every session id that has a ledger file for this project."""
    digest = _digest(project_root)
    seen: set[str] = set()
    candidates: list[Path] = [Path(STORAGE_BASE_DIR) / "chats" / digest]
    if project_root:
        candidates.append(Path(project_root) / IN_PROJECT_FOLDER / "chats" / digest)
    for base in candidates:
        if not base.exists():
            continue
        for child in base.glob("*.json"):
            seen.add(child.stem)
    return sorted(seen)
