"""User-controlled history indexing and minimal automatic issue retrieval."""

import asyncio
import json
import sqlite3

from fastmcp import Context, FastMCP
from fastmcp.server.middleware import Middleware
from mcp.types import TextContent

from context_broker.context_ttc.tasks.history_tasks import lookup_history, set_history_policy
from context_broker.delegation_ttc.tools.failure_tools import exception_reason, failure
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.blocking import run_blocking
from context_broker.server_ttc.tools.task_result import TaskResult


class HistoryRetrieval(Middleware):
    """Check issue history for question-bearing tools without preloading new sessions."""

    async def on_call_tool(self, context, call_next):
        arguments = context.message.arguments or {}
        keys = {
            "route_task": "task",
            "search_context": "query",
            "search_codebase": "query",
            "search_codebase_tool": "query",
            "find_in_codebase": "pattern",
        }
        key = keys.get(context.message.name)
        query = arguments.get(key, "") if key else ""
        history = None
        if isinstance(query, str) and query.strip():
            try:
                root = resolve_project_root(arguments.get("project_root", ""))
                history = await run_blocking(lookup_history, root, query)
            except (ValueError, OSError, sqlite3.Error) as exc:
                history = failure(exception_reason(exc), code="history_lookup_failed")
        result = await call_next(context)
        if history and (
            history.get("matches") or history.get("partial") or history.get("status") == "failed"
        ):
            # Append bounded evidence separately; preserve the original structured tool contract.
            result.content.append(
                TextContent(
                    type="text",
                    text="Project issue history:\n" + json.dumps(history, ensure_ascii=False),
                )
            )
        return result


def register_history_tools(mcp: FastMCP) -> None:
    """Offer indexing through actual user elicitation; no caller approval boolean."""

    mcp.add_middleware(HistoryRetrieval())

    @mcp.tool()
    async def configure_history_indexing(project_root: str = "", ctx: Context = None) -> TaskResult:
        """Ask the user Index / No index for this project's MCP history folder.

        No index still checks history directly for relevant prior issues. It deletes only
        the optional derived index, never chat records or handoffs. Call at setup or when
        the user wants to change this preference. Unsupported consent changes nothing.
        """
        try:
            root = resolve_project_root(project_root)
            choice = await asyncio.wait_for(
                ctx.elicit(
                    "Index this project's MCP history for faster repeated-issue lookup? "
                    "No index still reads history directly. Neither option preloads full history.",
                    response_type=["Index", "No index"],
                ),
                timeout=300,
            )
            if choice.action != "accept" or choice.data not in {"Index", "No index"}:
                return TaskResult(structured_content={"status": "unchanged"})
            result = await run_blocking(set_history_policy, root, choice.data == "Index")
        except TimeoutError:
            result = failure(
                "History indexing choice timed out; preference unchanged",
                code="confirmation_timeout",
            )
        except (ValueError, OSError, sqlite3.Error) as exc:
            result = failure(exception_reason(exc), code="history_configuration_failed")
        except Exception:
            result = failure(
                "Could not confirm or save history indexing choice; inspect project storage and client elicitation support",
                code="history_configuration_failed",
            )
        return TaskResult(structured_content=result)

    @mcp.tool()
    async def lookup_project_history(query: str, project_root: str = "") -> TaskResult:
        """Check this specific issue before new work. Return at most three relevant excerpts.

        Always reads/checks project history, even with indexing disabled. No match means
        no history is injected. Similarity is conservative keyword overlap, not a claim
        of semantic equivalence. Partial indicates scan limits or unreadable records.
        """
        try:
            result = await run_blocking(lookup_history, resolve_project_root(project_root), query)
        except (ValueError, OSError, sqlite3.Error) as exc:
            result = failure(exception_reason(exc), code="history_lookup_failed")
        return TaskResult(structured_content=result)
