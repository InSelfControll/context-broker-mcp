"""
Resource and prompt registration for MCP server.
"""

from context_broker.server_ttc.tools.blocking import run_blocking

from fastmcp import FastMCP

from context_broker.config import DEFAULT_QUERY
from context_broker.indexer import get_last_token_report, search_codebase
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import (
    format_search_summary_line,
    format_token_efficiency_lines,
    format_token_report_lines,
    report_from_result,
)
from context_broker.utils import log


def register_resources_and_prompts(mcp: FastMCP) -> None:
    """Register MCP resources and prompts."""

    @mcp.resource("codebase://auto-context")
    async def auto_context_resource() -> str:
        """Auto-provide code context on requests."""
        with tracked_activity():
            log("🔄 auto_context_resource called")
            root = resolve_project_root()
            try:
                result = await run_blocking(search_codebase, DEFAULT_QUERY, root, top_k=3)
                lines = [
                    format_search_summary_line(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                    ),
                    "",
                    f"🔄 Auto-Context: {result['project']}",
                    f"📂 Project Root: {result['project_root']}",
                    "",
                    *format_token_efficiency_lines(
                        result["total_tokens"],
                        result["context_tokens"],
                        result["saved_tokens"],
                        result["saved_percent"],
                        truncated_files=int(result.get("truncated_files", 0)),
                    ),
                    "",
                ]
                for item in result["results"]:
                    lines.append(f"### FILE: {item['path']}")
                    lines.append(item["content"])
                    lines.append("")
                return "\n".join(lines)
            except Exception as e:
                log(f"⚠️ Auto-context error: {e}", "WARN")
                return ""

    @mcp.resource("codebase://token-counter")
    async def token_counter_resource() -> str:
        """Provide latest token counter for editor dashboards."""
        with tracked_activity():
            log("📊 token_counter_resource called")
            root = resolve_project_root()
            report = await run_blocking(get_last_token_report, root)
            if report is None:
                try:
                    result = await run_blocking(search_codebase, DEFAULT_QUERY, root, top_k=1)
                    report = report_from_result(result)
                except Exception as e:
                    log(f"⚠️ token_counter_resource init error: {e}", "WARN")
                    return ""
            return "\n".join(
                format_token_report_lines(report, title="📊 Token Counter (Editor Integration)")
            )

    @mcp.prompt("auto-search")
    def auto_search_prompt() -> str:
        """Prompt requiring semantic code search before answer."""
        return """IMPORTANT: Before answering ANY user request about code, you MUST first call the `search_codebase` tool with:
- query: Extract the main topic/keywords from the user's request
- project_root: Optional - will be auto-detected from current directory

Alternatively, use `auto_search` tool for initial project exploration (no arguments needed).

For a large task with 2-4 independent assignments, offer `delegate_large_task`.
Ask which exact model to use if the user has not specified one. Include the original
request, conversation decisions, constraints, relevant files, and acceptance criteria.
The delegation tool asks the user whether to split or keep one agent. Never interpret
silence as consent. Do not split dependent work. If elicitation is unavailable or the
user declines, continue with one agent. Integrate proposals and run verification before
claiming completion; worker/reviewer prose is not proof that tests ran.

Before switching models, call save_model_handoff with exact messages, the original goal,
all decisions, constraints, facts, task outcomes and evidence, open questions, and criteria.
Pass its handoff_id to the next model and call load_model_handoff before continuing.
Never treat a failed load, missing memory, or a failed task as completed. Preserve the
user's model and reasoning preferences. Do not invent unsaved conversation history.

This ensures you have relevant codebase context before responding. Never skip this step."""
