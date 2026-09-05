"""
Token-viewer related MCP tool handlers.
"""

import json
from typing import Any

from context_broker.server_ttc.tools.blocking import run_blocking

from fastmcp import Context, FastMCP

from context_broker.config import DEFAULT_QUERY, EMBEDDING_MODEL, ENCODING_MODEL, MODEL_DEVICE
from context_broker.indexer import get_last_token_report, search_codebase
from context_broker.lifecycle import tracked_activity
from context_broker.project import get_project_name, resolve_project_root
from context_broker.server_ttc.tools.helpers import (
    format_search_summary_line,
    format_token_report_lines,
    progress,
    report_from_result,
)
from context_broker.storage import list_token_counter_runs
from context_broker.utils import log


def _reports_from_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract report payloads oldest-first for request timeline views."""
    reports: list[dict[str, Any]] = []
    for run in reversed(runs):
        report = run.get("report")
        if not isinstance(report, dict):
            continue
        reports.append(
            {
                "run_at": run.get("updated_at", ""),
                "filename": run.get("filename", ""),
                **report,
            }
        )
    return reports


def _format_token_history_graph(reports: list[dict[str, Any]]) -> list[str]:
    """Build a Markdown graph view that renders in clients with Mermaid support."""
    if not reports:
        return ["No token history found yet. Run a search first."]

    labels = [f"r{i + 1}" for i in range(len(reports))]
    saved_percent = [round(float(report.get("saved_percent", 0.0)), 1) for report in reports]
    reply_tokens = [int(report.get("context_tokens", 0)) for report in reports]
    not_sent_tokens = [int(report.get("saved_tokens", 0)) for report in reports]
    latest = reports[-1]

    return [
        "📉 Token Reduction By Request",
        f"Embedding model: {latest.get('embedding_model', '(unknown)')}",
        f"Token encoding: {latest.get('encoding_model', '(unknown)')}",
        "",
        "```mermaid",
        "xychart-beta",
        '    title "Token reduction by request"',
        f"    x-axis [{', '.join(labels)}]",
        '    y-axis "Saved %" 0 --> 100',
        f"    bar [{', '.join(str(value) for value in saved_percent)}]",
        "```",
        "",
        "Graph data:",
        f"- Requests: {len(reports)}",
        f"- Latest reply tokens: {reply_tokens[-1]:,}",
        f"- Latest not-sent tokens: {not_sent_tokens[-1]:,}",
        f"- Latest saved: {saved_percent[-1]:.1f}%",
        "",
        "JSON:",
        "```json",
        json.dumps(reports, indent=2, ensure_ascii=False),
        "```",
    ]


def register_token_tools(mcp: FastMCP) -> None:
    """Register token-counter tool."""

    @mcp.tool()
    async def token_counter(project_root: str = "", ctx: Context = None) -> str:
        """Get latest token usage report for editor integrations."""
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📊 token_counter called: project_root='{root_display}'")

            root = resolve_project_root(project_root)
            report = await run_blocking(get_last_token_report, root)
            if report is None:
                await progress(ctx, "📊 Initializing token counter with default context search...")
                result = await run_blocking(search_codebase, DEFAULT_QUERY, root, top_k=1)
                report = await run_blocking(get_last_token_report, root) or report_from_result(result)

            await progress(
                ctx,
                format_search_summary_line(
                    report["total_tokens"],
                    report["context_tokens"],
                    report["saved_tokens"],
                    report["saved_percent"],
                ),
            )
            return "\n".join(format_token_report_lines(report))

    @mcp.tool()
    async def token_history(project_root: str = "", limit: int = 20, ctx: Context = None) -> str:
        """Show graph-ready token savings history across search requests."""
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📉 token_history called: project_root='{root_display}', limit={limit}")

            root = resolve_project_root(project_root)
            project_name = get_project_name(root)
            safe_limit = min(max(limit, 1), 200)
            runs = await run_blocking(list_token_counter_runs, project_name, root, safe_limit)
            reports = _reports_from_runs(runs)
            await progress(ctx, f"📉 Loaded {len(reports)} token history runs")
            return "\n".join(_format_token_history_graph(reports))

    @mcp.tool()
    async def token_integration_manifest(project_root: str = "", ctx: Context = None) -> str:
        """Return integration options for GraphQL, LangGraph, and other agent runtimes."""
        with tracked_activity():
            root = resolve_project_root(project_root)
            project_name = get_project_name(root)
            log(f"🔌 token_integration_manifest called: project='{project_name}'")
            manifest = {
                "name": "context-broker-token-metrics",
                "version": 1,
                "project": project_name,
                "project_root": root,
                "models": {
                    "embedding_model": EMBEDDING_MODEL,
                    "encoding_model": ENCODING_MODEL,
                    "device": MODEL_DEVICE,
                },
                "mcp_tools": {
                    "search_codebase_tool": "Runs semantic search and writes a per-run token JSON.",
                    "auto_search": "Runs default project search and writes a per-run token JSON.",
                    "token_counter": "Returns the latest token report.",
                    "token_history": "Returns graph-ready request history with Mermaid and JSON.",
                    "token_integration_manifest": "Returns this machine-readable integration manifest.",
                },
                "storage": {
                    "latest_report": "_internal/token-counter-latest.json",
                    "run_history": "_internal/token-runs/token-run-*.json",
                    "token_baseline": "indexed-corpus-per-file-cap",
                },
                "graphql_adapter": {
                    "status": "ready-to-adapt",
                    "recommended_queries": [
                        "tokenCounter(projectRoot: String): TokenReport",
                        "tokenHistory(projectRoot: String, limit: Int = 20): [TokenReportRun!]!",
                    ],
                    "schema_hint": {
                        "TokenReport": {
                            "totalTokens": "Int!",
                            "contextTokens": "Int!",
                            "savedTokens": "Int!",
                            "savedPercent": "Float!",
                            "embeddingModel": "String!",
                            "encodingModel": "String!",
                        }
                    },
                },
                "langgraph_adapter": {
                    "status": "ready-to-adapt",
                    "recommended_node": "context_broker_token_metrics",
                    "inputs": ["project_root", "query", "limit"],
                    "outputs": ["latest_report", "history", "graph_markdown"],
                    "idempotency": (
                        "Read-only nodes should call token_counter/token_history; "
                        "search nodes create one run JSON per invocation."
                    ),
                },
            }
            await progress(ctx, "🔌 Built token integration manifest")
            return json.dumps(manifest, indent=2, ensure_ascii=False)
