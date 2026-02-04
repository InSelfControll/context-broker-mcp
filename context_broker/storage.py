"""
Storage Module

Handles persistence of search results with multiple storage modes:
- Global: Centralized storage in ~/.context-broker/
- In-project: Storage within each project directory
- Both: Uses both locations with local priority
"""

import json
from pathlib import Path
from typing import Any, Optional

from context_broker.config import (
    STORAGE_MODE, STORAGE_BASE_DIR, IN_PROJECT_FOLDER, StorageMode
)
from context_broker.utils import log


def get_storage_dirs(
    project_name: str, 
    subdir: str = "", 
    project_root: str = ""
) -> tuple[Optional[Path], Path]:
    """
    Get both storage directory paths (local and global) for a project.
    
    Args:
        project_name: Name of the project
        subdir: Optional subdirectory path
        project_root: Required for local storage
        
    Returns:
        Tuple of (local_path, global_path) - local_path may be None
    """
    # Global path (always available)
    global_path = Path(STORAGE_BASE_DIR) / project_name
    if subdir:
        global_path = global_path / subdir
    
    # Local path (requires project_root)
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
    create: bool = True
) -> Path:
    """
    Get the appropriate storage directory based on current storage mode.
    
    Three modes:
    1. "global": ~/.context-broker/{project-name}/{subdir}/
    2. "in-project": {project-root}/.context-broker/{subdir}/
    3. "both": Prefer local if available and prefer_local=True
    
    Args:
        project_name: Name of the project
        subdir: Optional subdirectory
        project_root: Required for in-project mode
        prefer_local: When in "both" mode, prefer local storage
        create: Whether to auto-create the directory
        
    Returns:
        Path to the storage directory
    """
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
    else:  # "both" mode
        if local_path and prefer_local:
            base = local_path
        else:
            base = global_path
    
    # Auto-create directory structure
    if create:
        base.mkdir(parents=True, exist_ok=True)
        
        # Create marker file
        marker_file = base / ".context-broker-marker"
        if not marker_file.exists():
            try:
                marker_file.write_text(
                    f"# Context Broker Storage\n"
                    f"# Project: {project_name}\n"
                    f"# Mode: {mode}\n"
                )
            except Exception:
                pass
    
    return base


def save_json_data(
    project_name: str,
    filename: str,
    data: Any,
    subdir: str = "",
    project_root: str = "",
    pretty: bool = True,
    save_to_both: bool = False
) -> str:
    """
    Save JSON data to a project-specific subdirectory.
    
    Args:
        project_name: Name of the project
        filename: Name of the JSON file
        data: Data to serialize (must be JSON-serializable)
        subdir: Optional subdirectory
        project_root: Required for in-project storage
        pretty: Whether to use pretty printing
        save_to_both: If True and mode is "both", save to both locations
        
    Returns:
        Path to the saved file(s)
    """
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    
    # Ensure .json extension
    if not filename.endswith(".json"):
        filename = filename + ".json"
    
    saved_paths: list[str] = []
    
    def do_save(base_path: Path) -> str:
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
        # Save to both locations
        if local_path:
            saved_paths.append(do_save(local_path))
        saved_paths.append(do_save(global_path))
        return ", ".join(saved_paths)
    else:
        # Save to preferred location
        storage_dir = get_storage_dir(project_name, subdir, project_root, prefer_local=True)
        return do_save(storage_dir)


def load_json_data(
    project_name: str,
    filename: str,
    subdir: str = "",
    project_root: str = "",
    check_both: bool = True
) -> Optional[Any]:
    """
    Load JSON data from a project-specific subdirectory.
    
    In "both" mode, checks local project first, then global.
    
    Args:
        project_name: Name of the project
        filename: Name of the JSON file
        subdir: Optional subdirectory
        project_root: Required for in-project storage
        check_both: If True, check both local and global locations
        
    Returns:
        The loaded data, or None if file doesn't exist
    """
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    
    # Ensure .json extension
    if not filename.endswith(".json"):
        filename = filename + ".json"
    
    def try_load(base_path: Optional[Path]) -> Optional[Any]:
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
    
    # In "both" mode, try local first, then global
    if mode == StorageMode.BOTH and check_both and local_path:
        data = try_load(local_path)
        if data is not None:
            log(f"📂 Loaded from local project: {local_path / filename}")
            return data
        # Fall through to global
    
    # Try the primary location based on mode
    if mode == StorageMode.IN_PROJECT and local_path:
        return try_load(local_path)
    else:
        return try_load(global_path)


def list_saved_json(
    project_name: str,
    subdir: str = "",
    project_root: str = "",
    merge_both: bool = True
) -> list[str]:
    """
    List all saved JSON files for a project.
    
    In "both" mode, returns merged files from both locations.
    
    Args:
        project_name: Name of the project
        subdir: Optional subdirectory
        project_root: Required for in-project storage
        merge_both: If True, merge results from both locations
        
    Returns:
        List of filenames
    """
    local_path, global_path = get_storage_dirs(project_name, subdir, project_root)
    
    def get_files(base_path: Optional[Path]) -> list[str]:
        if not base_path or not base_path.exists():
            return []
        return [f.name for f in base_path.glob("*.json")]
    
    local_files = get_files(local_path)
    global_files = get_files(global_path)
    
    mode = STORAGE_MODE.lower()
    
    if mode == StorageMode.BOTH and merge_both:
        # Merge and deduplicate, local files first
        all_files = list(dict.fromkeys(local_files + global_files))
        return all_files
    
    # Return based on mode
    if mode == StorageMode.IN_PROJECT:
        return local_files
    else:
        return global_files


def get_storage_config_info() -> dict[str, Any]:
    """
    Get current storage configuration as a dictionary.
    
    Returns:
        Dictionary with storage configuration details
    """
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
            "CONTEXT_BROKER_STORAGE_DIR": f"Base directory (default: ~/.context-broker)",
        }
    }
