"""
Generic JSON persistence tasks.
"""

import json
from typing import Any, Optional

from context_broker.config import IN_PROJECT_FOLDER, STORAGE_BASE_DIR, STORAGE_MODE, StorageMode
from context_broker.storage_ttc.tools.path_tools import get_storage_dir, get_storage_dirs
from context_broker.utils import log


def save_json_data(
    project_name: str,
    filename: str,
    data: Any,
    subdir: str = "",
    project_root: str = "",
    pretty: bool = True,
    save_to_both: bool = False,
) -> str:
    """Save JSON data to project storage directories."""
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    if not filename.endswith(".json"):
        filename = filename + ".json"

    def do_save(base_path) -> str:
        base_path.mkdir(parents=True, exist_ok=True)
        filepath = base_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)
        log(f"💾 Saved JSON to: {filepath}")
        return str(filepath)

    mode = STORAGE_MODE.lower()
    if mode == StorageMode.BOTH and save_to_both:
        saved_paths: list[str] = []
        if local_path:
            saved_paths.append(do_save(local_path))
        saved_paths.append(do_save(global_path))
        return ", ".join(saved_paths)

    return do_save(get_storage_dir(project_name, subdir, project_root, prefer_local=True))


def load_json_data(
    project_name: str,
    filename: str,
    subdir: str = "",
    project_root: str = "",
    check_both: bool = True,
) -> Optional[Any]:
    """Load JSON data from project storage directories."""
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    if not filename.endswith(".json"):
        filename = filename + ".json"

    def try_load(base_path) -> Optional[Any]:
        if not base_path:
            return None
        filepath = base_path / filename
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️ Failed to load JSON from {filepath}: {e}", "WARN")
            return None

    mode = STORAGE_MODE.lower()
    if mode == StorageMode.BOTH and check_both and local_path:
        data = try_load(local_path)
        if data is not None:
            log(f"📂 Loaded from local project: {local_path / filename}")
            return data
    if mode == StorageMode.IN_PROJECT and local_path:
        return try_load(local_path)
    return try_load(global_path)


def list_saved_json(
    project_name: str,
    subdir: str = "",
    project_root: str = "",
    merge_both: bool = True,
) -> list[str]:
    """List saved JSON files for a project."""
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)

    def get_files(base_path) -> list[str]:
        if not base_path or not base_path.exists():
            return []
        return [f.name for f in base_path.glob("*.json")]

    local_files = get_files(local_path)
    global_files = get_files(global_path)
    mode = STORAGE_MODE.lower()
    if mode == StorageMode.BOTH and merge_both:
        return list(dict.fromkeys(local_files + global_files))
    return local_files if mode == StorageMode.IN_PROJECT else global_files


def get_storage_config_info() -> dict[str, Any]:
    """Get current storage configuration details."""
    return {
        "mode": STORAGE_MODE,
        "base_dir": STORAGE_BASE_DIR,
        "in_project_folder": IN_PROJECT_FOLDER,
        "modes": {
            StorageMode.GLOBAL: "Store only in centralized location",
            StorageMode.IN_PROJECT: "Store only in project folder",
            StorageMode.BOTH: "Use both, prefer local project (DEFAULT)",
        },
        "environment_variables": {
            "CONTEXT_BROKER_STORAGE_MODE": "'global', 'in-project', or 'both'",
            "CONTEXT_BROKER_STORAGE_DIR": "Base directory (default: ~/.context-broker)",
        },
    }
