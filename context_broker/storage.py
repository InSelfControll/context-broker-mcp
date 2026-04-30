"""
Compatibility wrapper for storage API.
"""

from context_broker.storage_ttc.codebase.api import (
    get_storage_config_info,
    get_storage_dir,
    get_storage_dirs,
    list_token_counter_runs,
    list_saved_json,
    load_json_data,
    load_token_counter_report,
    save_json_data,
    save_token_counter_report,
    save_token_counter_run,
)

__all__ = [
    "get_storage_dirs",
    "get_storage_dir",
    "save_json_data",
    "load_json_data",
    "list_saved_json",
    "get_storage_config_info",
    "save_token_counter_report",
    "save_token_counter_run",
    "load_token_counter_report",
    "list_token_counter_runs",
]
