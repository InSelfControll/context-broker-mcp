"""
Generic JSON persistence tasks.
"""

import json
from typing import Any, Optional

from context_broker.config import IN_PROJECT_FOLDER, STORAGE_BASE_DIR, STORAGE_MODE, StorageMode
from context_broker.security_ttc.tools import is_secret_file
from context_broker.storage_ttc.tools.path_tools import (
    get_storage_dir,
    get_storage_dirs,
    sanitize_storage_component,
)
from context_broker.utils import log


def _validate_filename(filename: str) -> str:
    """Validate an MCP-supplied storage filename before any read/write."""
    cleaned = sanitize_storage_component(filename, kind="filename")
    is_secret, reason = is_secret_file(cleaned, cleaned)
    if is_secret:
        raise ValueError(f"Invalid filename: {reason}")
    return cleaned


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
    filename = _validate_filename(filename)
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
    filename = _validate_filename(filename)
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
            log(f"⚠ Failed to load JSON from {filepath}: {e}", "WARN")
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
    from context_broker.config import (
        ACCOUNT_NAME_OVERRIDE,
        CHAT_CACHE_TTL_SECONDS,
        DASHBOARD_HOST,
        DASHBOARD_PORT,
        EMBEDDING_MODEL,
        CONTEXT_BACKEND,
        HONCHO_ASSISTANT_PEER_ID,
        HONCHO_CONTEXT_TOKENS,
        HONCHO_LIMIT_TO_SESSION,
        HONCHO_SESSION_PREFIX,
        HONCHO_USER_PEER_ID,
        HONCHO_WORKSPACE_ID,
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        MODEL_DEVICE,
        REDIS_KEY_PREFIX,
        REDIS_URL,
        USE_ACCOUNT_NAME,
    )
    from context_broker.identity import resolve_user_peer_id

    return {
        "mode": STORAGE_MODE,
        "base_dir": STORAGE_BASE_DIR,
        "in_project_folder": IN_PROJECT_FOLDER,
        "modes": {
            StorageMode.GLOBAL: "Store only in centralized location",
            StorageMode.IN_PROJECT: "Store only in project folder",
            StorageMode.BOTH: "Use both, prefer local project (DEFAULT)",
        },
        "model": {
            "embedding_model": EMBEDDING_MODEL,
            "device": MODEL_DEVICE,
            "llm_model": LLM_MODEL or "(not set)",
            "llm_base_url": LLM_BASE_URL or "(not set)",
            "llm_api_key": "(set)" if LLM_API_KEY else "(not set)",
        },
        "cache": {
            "backend": "local-json",
        },
        "context": {
            "backend": CONTEXT_BACKEND,
            "honcho_workspace_id": HONCHO_WORKSPACE_ID,
            "honcho_session_prefix": HONCHO_SESSION_PREFIX,
            "honcho_user_peer_id": HONCHO_USER_PEER_ID,
            "honcho_assistant_peer_id": HONCHO_ASSISTANT_PEER_ID,
            "honcho_context_tokens": HONCHO_CONTEXT_TOKENS,
            "honcho_limit_to_session": HONCHO_LIMIT_TO_SESSION,
            "redis_url": "(set)" if REDIS_URL else "(not set)",
            "redis_key_prefix": REDIS_KEY_PREFIX,
            "chat_cache_ttl_seconds": CHAT_CACHE_TTL_SECONDS,
        },
        "identity": {
            "use_account_name": USE_ACCOUNT_NAME,
            "account_name_override": ACCOUNT_NAME_OVERRIDE or "(not set)",
            "resolved_user_peer_id": resolve_user_peer_id(),
        },
        "dashboard": {
            "host": DASHBOARD_HOST,
            "port": DASHBOARD_PORT,
        },
        "environment_variables": {
            "CONTEXT_BROKER_STORAGE_MODE": "'global', 'in-project', or 'both'",
            "CONTEXT_BROKER_STORAGE_DIR": "Base directory (default: ~/.context-broker)",
            "CONTEXT_BROKER_EMBEDDING_MODEL": "Sentence-transformers model (default: all-MiniLM-L6-v2)",
            "CONTEXT_BROKER_DEVICE": "Torch device: cpu, cuda, mps (default: cpu)",
            "CONTEXT_BROKER_LLM_MODEL": "Optional LLM model identifier",
            "CONTEXT_BROKER_LLM_BASE_URL": "Optional LLM API base URL",
            "CONTEXT_BROKER_LLM_API_KEY": "Optional LLM API key",
            "CONTEXT_BROKER_CONTEXT_BACKEND": "'none', 'honcho', or 'redis' for cross-chat context",
            "CONTEXT_BROKER_REDIS_URL": "Redis URL when CONTEXT_BACKEND=redis",
            "CONTEXT_BROKER_REDIS_KEY_PREFIX": "Redis key prefix (default: context-broker)",
            "CONTEXT_BROKER_CHAT_CACHE_TTL_SECONDS": "Redis chat-payload cache TTL in seconds (0 disables, default 300)",
            "CONTEXT_BROKER_INDEX_FOLLOW_SYMLINKS": "Follow directory/file symlinks while indexing (default 0 — avoids /nix/store walks)",
            "CONTEXT_BROKER_INDEX_MAX_FILE_BYTES": "Skip files larger than N bytes when collecting (default 2000000, 0 disables)",
            "CONTEXT_BROKER_INDEX_DISK_CACHE": "Persist corpus embeddings under .cache/ (default 1)",
            "CONTEXT_BROKER_USE_ACCOUNT_NAME": "Use the OS account name as the default user peer id ('1'/'0')",
            "CONTEXT_BROKER_ACCOUNT_NAME_OVERRIDE": "Explicit override for the resolved account name (takes priority over getpass)",
            "CONTEXT_BROKER_DASHBOARD_HOST": "Bind host for the web dashboard (default: 127.0.0.1)",
            "CONTEXT_BROKER_DASHBOARD_PORT": "Bind port for the web dashboard (default: 8770)",
            "CONTEXT_BROKER_HONCHO_WORKSPACE_ID": "Honcho workspace id",
            "CONTEXT_BROKER_HONCHO_SESSION_PREFIX": "Prefix for Honcho session ids",
            "CONTEXT_BROKER_HONCHO_USER_PEER_ID": "Default user peer id",
            "CONTEXT_BROKER_HONCHO_ASSISTANT_PEER_ID": "Default assistant peer id",
            "CONTEXT_BROKER_HONCHO_CONTEXT_TOKENS": "Default Honcho context token budget",
            "CONTEXT_BROKER_HONCHO_LIMIT_TO_SESSION": "Limit Honcho context to selected session",
        },
    }
