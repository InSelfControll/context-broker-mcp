"""
Search-related MCP tool handlers.
"""

from context_broker.server_ttc.tools.blocking import run_blocking

from fastmcp import Context, FastMCP

from context_broker.indexer import literal_search, search_codebase
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
                result = await run_blocking(search_codebase, query, root, top_k=5)
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
                result = await run_blocking(search_codebase,
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

    @mcp.tool()
    async def find_in_codebase(
        pattern: str,
        project_root: str = "",
        case_sensitive: bool = False,
        use_regex: bool = False,
        file_glob: str = "",
        ctx: Context = None,
    ) -> str:
        """Find exact literal or regex pattern matches in the codebase.

        Runs entirely locally — no embedding model, no external LLM call.
        Returns file paths, line numbers, and context snippets for each match.
        Use this instead of search_codebase_tool when you need precise text
        matches (e.g. "session_id", "def authenticate", a specific import).
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(
                f"🔎 find_in_codebase called: pattern='{pattern[:50]}...', "
                f"root='{root_display}', regex={use_regex}"
            )
            await progress(ctx, f"🔎 Searching for: '{pattern[:60]}'")

            root = resolve_project_root(project_root)
            try:
                result = await run_blocking(literal_search,
                    pattern,
                    root,
                    case_sensitive=case_sensitive,
                    use_regex=use_regex,
                    file_glob=file_glob,
                )

                if result["total_matches"] == 0:
                    msg = f"❌ No matches found for '{pattern}' in {result['files_searched']} files."
                    await progress(ctx, msg)
                    return msg

                await progress(
                    ctx,
                    f"✅ Found {result['total_matches']} matches in "
                    f"{result['files_with_matches']} files",
                )

                lines = [
                    f"🔎 Literal Search Results for: '{pattern}'",
                    f"📁 Project: {result['project']}",
                    f"📂 Project Root: {result['project_root']}",
                    f"📊 {result['total_matches']} matches in "
                    f"{result['files_with_matches']}/{result['files_searched']} files",
                    f"🔧 Mode: {'regex' if use_regex else 'literal'}"
                    f"{', case-sensitive' if case_sensitive else ', case-insensitive'}",
                    "",
                    "=" * 60,
                    "",
                ]

                for file_result in result["results"]:
                    lines.append(f"### {file_result['relative_path']} ({file_result['match_count']} match(es))")
                    for m in file_result["matches"]:
                        lines.append(f"  L{m['line']}: {m['snippet']}")
                    lines.append("")

                if result["truncated"]:
                    lines.append("⚠️ Results truncated — use a narrower pattern or file_glob to see more.")

                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Literal search error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {str(e)}"
