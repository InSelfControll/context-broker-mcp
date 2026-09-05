"""
Storage path helpers and mode routing.
"""

from pathlib import Path, PureWindowsPath
from typing import Optional

from context_broker.config import IN_PROJECT_FOLDER, STORAGE_BASE_DIR, STORAGE_MODE, StorageMode
from context_broker.utils import log


def contained_path(base: Path, *parts: str) -> Path:
    """Resolve relative storage components without traversal or symlink escapes."""
    for part in parts:
        if (
            Path(part).is_absolute()
            or PureWindowsPath(part).drive
            or "\\" in part
            or ".." in Path(part).parts
            or "\x00" in part
        ):
            raise ValueError("storage paths must be relative and stay inside storage")
    candidate = base.joinpath(*parts)
    if not candidate.resolve().is_relative_to(base.resolve()):
        raise ValueError("storage path escapes its storage directory")
    return candidate


def get_storage_dirs(
    project_name: str, subdir: str = "", project_root: str = ""
) -> tuple[Optional[Path], Path]:
    """Get local and global storage directories for a project."""
    if not project_name or project_name in {".", ".."} or "/" in project_name:
        raise ValueError("project_name must be a non-empty directory name")
    global_path = contained_path(Path(STORAGE_BASE_DIR), project_name, subdir)

    local_path: Optional[Path] = None
    if project_root:
        local_path = contained_path(Path(project_root), IN_PROJECT_FOLDER)
        local_path = contained_path(local_path, subdir)
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
            log("⚠️ project_root required for in-project storage, falling back to global", "WARN")
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
