"""
Shared helpers for server task modules.
"""

from typing import Any

from fastmcp import Context

from context_broker.config import ENABLE_PROGRESS_NOTIFICATIONS
from context_broker.utils import log


def report_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize token report structure from search results."""
    return {
        "query": result.get("query", ""),
        "project": result.get("project", "unknown"),
        "project_root": result.get("project_root", ""),
        "total_tokens": result.get("total_tokens", 0),
        "context_tokens": result.get("context_tokens", 0),
        "saved_tokens": result.get("saved_tokens", 0),
        "saved_percent": result.get("saved_percent", 0.0),
        "returned_files": result.get("returned_files", 0),
        "truncated_files": result.get("truncated_files", 0),
        "total_files": result.get("total_files", 0),
        "from_cache": result.get("from_cache", False),
    }


def format_token_report_lines(report: dict[str, Any], title: str = "📊 Token Counter") -> list[str]:
    """Build human-readable token report lines."""
    return [
        title,
        f"📁 Project: {report.get('project', 'unknown')}",
        f"📂 Project Root: {report.get('project_root', '')}",
        f"🔎 Last Query: {report.get('query', '')}",
        "",
        "📈 Token Efficiency Report:",
        f"   • Total Project Tokens: {int(report.get('total_tokens', 0)):,}",
        f"   • Context Sent: {int(report.get('context_tokens', 0)):,}",
        f"   • Tokens Saved: {int(report.get('saved_tokens', 0)):,} ({float(report.get('saved_percent', 0.0)):.1f}%)",
        f"   • Returned Files: {int(report.get('returned_files', 0))}",
        f"   • Snippets Truncated: {int(report.get('truncated_files', 0))}",
        f"   • From Cache: {report.get('from_cache', False)}",
        "",
    ]


async def progress(ctx: Context | None, message: str) -> None:
    """Send optional progress notifications to the MCP client."""
    if not ctx or not ENABLE_PROGRESS_NOTIFICATIONS:
        return
    try:
        await ctx.info(message)
    except Exception as e:
        log(f"⚠️ Failed to send MCP progress notification: {e}", "WARN")


async def notify_error(ctx: Context | None, message: str) -> None:
    """Send error notifications to the MCP client when available."""
    if not ctx:
        return
    try:
        await ctx.error(message)
    except Exception as e:
        log(f"⚠️ Failed to send MCP error notification: {e}", "WARN")
