"""
Search-related MCP tool handlers.
"""

from fastmcp import Context, FastMCP

from context_broker.indexer import search_codebase
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import (
    format_search_summary_line,
    format_token_efficiency_lines,
    notify_error,
    progress,
)
from context_broker.utils import log


def register_search_tools(mcp: FastMCP) -> None:
    """Register semantic-search related tools."""

    @mcp.tool()
    async def search_codebase_tool(query: str, project_root: str = "", ctx: Context = None) -> str:
        """Search the codebase using semantic similarity."""
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(
                f"🔍 search_codebase_tool called: query='{query[:50]}...', project_root='{root_display}'"
            )
            await progress(ctx, f"🔍 Searching codebase for: '{query[:60]}...'")

            root = resolve_project_root(project_root)
            try:
                await progress(ctx, f"📁 Project root resolved to: {root}")
                result = search_codebase(query, root, top_k=5)
                tok_line = format_search_summary_line(
                    result["total_tokens"],
                    result["context_tokens"],
                    result["saved_tokens"],
                    result["saved_percent"],
                )
                await progress(ctx, f"✅ {tok_line} · files: {result['returned_files']}")

                lines = [
                    format_search_summary_line(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                    ),
                    "",
                    f"🔍 Search Results for: '{result['query']}'",
                    f"📁 Project: {result['project']}",
                    f"📂 Project Root: {result['project_root']}",
                    f"📊 Found {result['returned_files']} relevant files (out of {result['total_files']} total)",
                    "",
                    *format_token_efficiency_lines(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                        truncated_files=int(result.get("truncated_files", 0)),
                    ),
                    "",
                    "=" * 60,
                    "",
                ]

                for item in result["results"]:
                    lines.append(f"### FILE: {item['path']}")
                    lines.append(item["content"])
                    lines.append("")
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Search error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {str(e)}"

    @mcp.tool()
    async def auto_search(project_root: str = "", ctx: Context = None) -> str:
        """Auto-search for entry points and configuration."""
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"🚀 auto_search called: project_root='{root_display}'")
            await progress(ctx, "🚀 Auto-searching for project entry points and configuration...")

            root = resolve_project_root(project_root)
            try:
                result = search_codebase(
                    "main entry point configuration setup architecture",
                    root,
                    top_k=5,
                )
                tok_line = format_search_summary_line(
                    result["total_tokens"],
                    result["context_tokens"],
                    result["saved_tokens"],
                    result["saved_percent"],
                )
                await progress(ctx, f"✅ {tok_line} · files: {result['returned_files']}")

                lines = [
                    format_search_summary_line(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                    ),
                    "",
                    f"🚀 Auto-Context for Project: {result['project']}",
                    f"📂 Project Root: {result['project_root']}",
                    f"📊 Found {result['returned_files']} relevant files",
                    "",
                    *format_token_efficiency_lines(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                        truncated_files=int(result.get("truncated_files", 0)),
                    ),
                    "",
                    "=" * 60,
                    "",
                ]
                for item in result["results"]:
                    lines.append(f"### FILE: {item['path']}")
                    lines.append(item["content"])
                    lines.append("")
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Auto-search error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {str(e)}"
