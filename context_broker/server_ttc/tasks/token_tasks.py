"""
Token-viewer related MCP tool handlers.
"""

from fastmcp import Context, FastMCP

from context_broker.config import DEFAULT_QUERY
from context_broker.indexer import get_last_token_report, search_codebase
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import (
    format_token_report_lines,
    progress,
    report_from_result,
)
from context_broker.utils import log


def register_token_tools(mcp: FastMCP) -> None:
    """Register token-counter tool."""

    @mcp.tool()
    async def token_counter(project_root: str = "", ctx: Context = None) -> str:
        """Get latest token usage report for editor integrations."""
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📊 token_counter called: project_root='{root_display}'")

            root = resolve_project_root(project_root)
            report = get_last_token_report(root)
            if report is None:
                await progress(ctx, "📊 Initializing token counter with default context search...")
                result = search_codebase(DEFAULT_QUERY, root, top_k=1)
                report = report_from_result(result)

            await progress(
                ctx,
                f"📈 Tokens: total={report['total_tokens']:,}, sent={report['context_tokens']:,}, saved={report['saved_percent']:.1f}%",
            )
            return "\n".join(format_token_report_lines(report))
