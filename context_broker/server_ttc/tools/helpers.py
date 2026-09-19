"""
Shared helpers for server task modules.
"""

import asyncio
from typing import Any

from fastmcp import Context

from context_broker.config import (
    ENABLE_PROGRESS_NOTIFICATIONS,
    ENCODING_MODEL,
    INDEX_FILE_MAX_CHARS,
    RESULT_FILE_MAX_CHARS,
)
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


def format_token_efficiency_lines(
    total_tokens: int,
    context_tokens: int,
    saved_tokens: int,
    saved_percent: float,
    *,
    truncated_files: int | None = None,
) -> list[str]:
    """User-facing token breakdown (same baseline as indexer search_tasks)."""
    per_file_cap = max(INDEX_FILE_MAX_CHARS, RESULT_FILE_MAX_CHARS)
    lines = [
        f"📈 Token estimate ({ENCODING_MODEL})",
        f"   • Indexed corpus: {total_tokens:,} tokens (per indexed file ≤{per_file_cap:,} chars; ignores applied)",
        f"   • This reply: {context_tokens:,} tokens (snippets below)",
        f"   • Not sent vs full indexed corpus: {saved_tokens:,} tokens ({saved_percent:.1f}%)",
    ]
    if truncated_files is not None:
        lines.append(f"   • Snippets truncated to per-file cap: {truncated_files}")
    return lines


def format_search_summary_line(
    total_tokens: int,
    context_tokens: int,
    saved_tokens: int,
    saved_percent: float,
) -> str:
    """Single line for tool output headers and MCP progress."""
    return (
        f"📊 Tokens — reply: {context_tokens:,} | indexed corpus: {total_tokens:,} "
        f"| not sent: {saved_tokens:,} ({saved_percent:.1f}%)"
    )


def format_token_report_lines(report: dict[str, Any], title: str = "📊 Token Counter") -> list[str]:
    """Build human-readable token report lines."""
    return [
        title,
        f"📁 Project: {report.get('project', 'unknown')}",
        f"📂 Project Root: {report.get('project_root', '')}",
        f"🔎 Last Query: {report.get('query', '')}",
        "",
        *format_token_efficiency_lines(
            int(report.get("total_tokens", 0)),
            int(report.get("context_tokens", 0)),
            int(report.get("saved_tokens", 0)),
            float(report.get("saved_percent", 0.0)),
            truncated_files=int(report.get("truncated_files", 0)),
        ),
        f"   • Returned files: {int(report.get('returned_files', 0))}",
        f"   • From cache: {report.get('from_cache', False)}",
        "",
    ]


async def progress(ctx: Context | None, message: str) -> None:
    """Send optional progress notifications to the MCP client."""
    if not ctx or not ENABLE_PROGRESS_NOTIFICATIONS:
        return
    try:
        await ctx.info(message)
    except Exception as e:
        log(f"⚠ Failed to send MCP progress notification: {e}", "WARN")


async def notify_error(ctx: Context | None, message: str) -> None:
    """Send error notifications to the MCP client when available."""
    if not ctx:
        return
    try:
        await ctx.error(message)
    except Exception as e:
        log(f"⚠ Failed to send MCP error notification: {e}", "WARN")


def stream_progress(ctx: Context | None, message: str) -> None:
    """Schedule an MCP progress notification from synchronous code.

    Index building and search run synchronously inside async tool handlers,
    so they cannot ``await progress(...)`` directly. This schedules the
    notification on the running event loop; it is delivered the next time the
    handler yields. Safe no-op when there is no running loop or no ctx.
    """
    if not ctx or not ENABLE_PROGRESS_NOTIFICATIONS:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(progress(ctx, message))
