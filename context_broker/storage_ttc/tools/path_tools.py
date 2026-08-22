"""
Storage path helpers and mode routing.
"""

import re
from pathlib import Path
from typing import Optional

from context_broker.config import IN_PROJECT_FOLDER, STORAGE_BASE_DIR, STORAGE_MODE, StorageMode
from context_broker.utils import log

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def sanitize_storage_component(
    value: str, *, kind: str, allow_nested: bool = False
) -> str:
    """Validate a caller-controlled storage path component.

    Rejects absolute paths, drive-letter prefixes, and ``..`` traversal so
    MCP-supplied project names, subdirectories, and filenames cannot escape
    the approved storage roots. Returns the cleaned relative path.
    """
    if not value:
        return value
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_PREFIX.match(value):
        raise ValueError(f"Invalid {kind}: absolute paths are not allowed")
    parts = [segment for segment in normalized.split("/") if segment not in ("", ".")]
    if not parts or any(segment == ".." for segment in parts):
        raise ValueError(f"Invalid {kind}: path traversal is not allowed")
    if not allow_nested and len(parts) > 1:
        raise ValueError(f"Invalid {kind}: must be a single path component")
    return "/".join(parts)


def get_storage_dirs(
    project_name: str, subdir: str = "", project_root: str = ""
) -> tuple[Optional[Path], Path]:
    """Get local and global storage directories for a project."""
    project_name = sanitize_storage_component(project_name, kind="project_name")
    subdir = sanitize_storage_component(subdir, kind="subdir", allow_nested=True)
    global_path = Path(STORAGE_BASE_DIR) / project_name
    if subdir:
        global_path = global_path / subdir

    local_path: Optional[Path] = None
    if project_root:
        local_path = Path(project_root) / IN_PROJECT_FOLDER
        if subdir:
            local_path = local_path / subdir
    return local_path, global_path


def get_storage_dir(
    project_name: str,
    subdir: str = "",
    project_root: str = "",
    prefer_local: bool = True,
    create: bool = True,
) -> Path:
    """Resolve active storage directory based on current storage mode."""
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    mode = STORAGE_MODE.lower()
    if mode == StorageMode.IN_PROJECT:
        if not local_path:
            log("⚠ project_root required for in-project storage, falling back to global", "WARN")
            base = global_path
        else:
            base = local_path
    elif mode == StorageMode.GLOBAL:
        base = global_path
    else:
        base = local_path if (local_path and prefer_local) else global_path

    if create:
        base.mkdir(parents=True, exist_ok=True)
        marker_file = base / ".context-broker-marker"
        if not marker_file.exists():
            try:
                marker_file.write_text(
                    f"# Context Broker Storage\n# Project: {project_name}\n# Mode: {mode}\n"
                )
            except Exception:
                pass
    return base
