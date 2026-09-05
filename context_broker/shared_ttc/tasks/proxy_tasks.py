"""Lightweight stdio proxy: no embedding model is imported in agent processes."""

import json

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from context_broker.server_ttc.tools.task_result import TaskResult

from pathlib import Path
from urllib.parse import quote

from context_broker.shared_ttc.tools.runtime_tools import read_service
from context_broker.shared_ttc.tools.scope import PROJECT_HEADER


class PreserveTaskFailures(Middleware):
    """Restore structured delegation errors flattened by FastMCP's ProxyTool."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ToolError as exc:
            if context.message.name not in {
                "delegate_large_task",
                "save_model_handoff",
                "load_model_handoff",
            "lookup_project_history",
            "configure_history_indexing",
            }:
                raise
            try:
                record = json.loads(str(exc))
            except (ValueError, TypeError):
                raise exc
            if (
                not isinstance(record, dict)
                or record.get("status") != "failed"
                or record.get("completed") is not False
                or not isinstance(record.get("failure_reason"), str)
            ):
                raise exc
            return TaskResult(structured_content=record)


def create_agent_proxy(project_root: str, service: dict[str, str] | None = None):
    """Create an agent-local MCP surface bound to a single canonical project."""
    import httpx
    from functools import partial

    from fastmcp.client.transports.http import StreamableHttpTransport
    from fastmcp.server import create_proxy
    from fastmcp.server.providers.proxy import ProxyClient

    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project_root must be a directory")
    service = service if service is not None else read_service()
    transport = StreamableHttpTransport(
        service["url"],
        auth=service["token"],
        headers={PROJECT_HEADER: quote(str(root), safe="")},
        httpx_client_factory=partial(httpx.AsyncClient, trust_env=False),
    )
    proxy = create_proxy(ProxyClient(transport), name="Context Broker Shared Connection")
    proxy.add_middleware(PreserveTaskFailures())
    return proxy


def run_agent_proxy(project_root: str) -> None:
    """End only this connection when its coding agent closes stdio."""
    from context_broker.lifecycle import _start_stdio_disconnect_watchdog

    _start_stdio_disconnect_watchdog()
    create_agent_proxy(project_root).run(transport="stdio", show_banner=False)
