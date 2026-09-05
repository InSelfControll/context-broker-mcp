"""Lightweight stdio proxy: no embedding model is imported in agent processes."""

from pathlib import Path
from urllib.parse import quote

from context_broker.shared_ttc.tools.runtime_tools import read_service
from context_broker.shared_ttc.tools.scope import PROJECT_HEADER


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
    return create_proxy(ProxyClient(transport), name="Context Broker Shared Connection")


def run_agent_proxy(project_root: str) -> None:
    """End only this connection when its coding agent closes stdio."""
    from context_broker.lifecycle import _start_stdio_disconnect_watchdog

    _start_stdio_disconnect_watchdog()
    create_agent_proxy(project_root).run(transport="stdio", show_banner=False)
