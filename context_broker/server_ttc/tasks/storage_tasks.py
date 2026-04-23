"""
Storage-related MCP tool handlers.
"""

import os

from fastmcp import Context, FastMCP

from context_broker.config import STORAGE_MODE, StorageMode
from context_broker.indexer import search_codebase
from context_broker.lifecycle import tracked_activity
from context_broker.project import get_project_name, resolve_project_root
from context_broker.server_ttc.tools.helpers import (
    format_token_efficiency_lines,
    notify_error,
    progress,
)
from context_broker.storage import (
    get_storage_config_info,
    list_saved_json,
    load_json_data,
    save_json_data,
)
from context_broker.utils import log


def register_storage_tools(mcp: FastMCP) -> None:
    """Register save/load/list/config tools."""

    @mcp.tool()
    async def save_search_results(
        query: str = "",
        filename: str = "",
        project_root: str = "",
        subdir: str = "",
        top_k: int = 5,
        ctx: Context = None,
    ) -> str:
        """Search and save results to JSON."""
        with tracked_activity():
            await progress(ctx, f"💾 Saving search results for: '{query[:50]}...'")
            if not query:
                return "❌ Error: query is required"
            if not filename:
                return "❌ Error: filename is required"

            root = resolve_project_root(project_root)
            project_name = get_project_name(root)
            log(
                f"💾 save_search_results called: query='{query[:50]}...', filename='{filename}', project='{project_name}'"
            )

            try:
                result = search_codebase(query, root, top_k)
                await progress(ctx, f"📊 Found {len(result['results'])} files to save")
                data = {
                    "project": project_name,
                    "project_root": root,
                    "query": query,
                    "storage_mode": STORAGE_MODE,
                    "top_k": top_k,
                    "timestamp": str(os.times().system),
                    "file_count": len(result["results"]),
                    "files": [
                        {"path": item["path"], "content": item["content"]}
                        for item in result["results"]
                    ],
                    "statistics": {
                        "total_tokens": result["total_tokens"],
                        "context_tokens": result["context_tokens"],
                        "saved_tokens": result["saved_tokens"],
                        "saved_percent": result["saved_percent"],
                        "truncated_files": result.get("truncated_files", 0),
                    },
                }
                filepath = save_json_data(project_name, filename, data, subdir, root)
                success_msg = f"✅ Saved {len(result['results'])} files to: {filepath}"
                log(success_msg)
                await progress(ctx, success_msg)
                return success_msg
            except Exception as e:
                error_msg = f"❌ Error saving results: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def list_saved_results(
        project_name: str,
        subdir: str = "",
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """List saved JSON results for a project."""
        with tracked_activity():
            log(f"📋 list_saved_results called: project_name='{project_name}', subdir='{subdir}'")
            await progress(ctx, f"📋 Listing saved results for project: {project_name}")
            if not project_name:
                return "❌ Error: project_name is required"

            try:
                files = list_saved_json(project_name, subdir, project_root)
                if not files:
                    subdir_msg = f" in '{subdir}'" if subdir else ""
                    msg = f"📭 No saved results found for project '{project_name}'{subdir_msg}."
                    log(msg)
                    return msg

                lines = [
                    f"📁 Saved Results for: {project_name}",
                    f"📦 Storage Mode: {STORAGE_MODE}",
                    "",
                ]
                for filename in files:
                    lines.append(f"  📄 {filename}")
                lines.extend(["", f"Total: {len(files)} files"])
                result = "\n".join(lines)
                log(f"📋 Found {len(files)} saved results")
                return result
            except Exception as e:
                error_msg = f"❌ Error listing results: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def load_saved_results(
        project_name: str,
        filename: str,
        subdir: str = "",
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Load previously saved search results."""
        with tracked_activity():
            log(
                f"📂 load_saved_results called: project_name='{project_name}', filename='{filename}'"
            )
            await progress(ctx, f"📂 Loading saved results: {filename}")
            if not project_name:
                return "❌ Error: project_name is required"
            if not filename:
                return "❌ Error: filename is required"

            try:
                data = load_json_data(project_name, filename, subdir, project_root)
                if data is None:
                    hint = ""
                    if STORAGE_MODE == StorageMode.IN_PROJECT and not project_root:
                        hint = "\n💡 Hint: In 'in-project' mode, you need to provide project_root"
                    msg = f"❌ File not found: {filename}{hint}"
                    log(msg, "WARN")
                    return msg

                await progress(ctx, f"✅ Loaded {data.get('file_count', 0)} files from {filename}")
                stats = data.get("statistics", {})
                lines = [
                    "📋 Saved Search Results",
                    f"Project: {data.get('project', 'unknown')}",
                    f"Query: {data.get('query', 'unknown')}",
                    f"Storage Mode: {data.get('storage_mode', 'unknown')}",
                    f"Files: {data.get('file_count', 0)}",
                    "",
                ]
                if stats:
                    lines.append("📈 Token snapshot (when results were saved):")
                    lines.extend(
                        format_token_efficiency_lines(
                            int(stats.get("total_tokens", 0)),
                            int(stats.get("context_tokens", 0)),
                            int(stats.get("saved_tokens", 0)),
                            float(stats.get("saved_percent", 0.0)),
                            truncated_files=int(stats.get("truncated_files", 0)),
                        )
                    )
                    lines.append("")
                lines.extend(["=" * 50, ""])
                for file_info in data.get("files", []):
                    lines.append(f"### FILE: {file_info['path']}")
                    lines.append(file_info.get("content", ""))
                    lines.append("")
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error loading results: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def get_storage_config(ctx: Context = None) -> str:
        """Get current storage configuration."""
        with tracked_activity():
            log("⚙️ get_storage_config called")
            await progress(ctx, "⚙️ Retrieving storage configuration...")
            config = get_storage_config_info()
            lines = [
                "📦 Context Broker Storage Configuration",
                "",
                f"Current Mode: {config['mode']}",
                "",
                "Available Modes:",
            ]
            for mode, description in config["modes"].items():
                marker = " ✅ DEFAULT" if mode == config["mode"] else ""
                lines.append(f"  • '{mode}' - {description}{marker}")
            lines.extend(
                [
                    "",
                    f"Base Directory (global): {config['base_dir']}",
                    f"In-Project Folder Name: {config['in_project_folder']}",
                    "",
                    "Environment Variables:",
                ]
            )
            for var, desc in config["environment_variables"].items():
                lines.append(f"  {var}")
                lines.append(f"    {desc}")
            return "\n".join(lines)
