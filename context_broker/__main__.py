"""
Entry point for running as a module: python -m context_broker

Subcommands:
    (default)   Run the MCP server (transport via CONTEXT_BROKER_TRANSPORT).
    dashboard   Run ONLY the web dashboard (web-only) on
                CONTEXT_BROKER_DASHBOARD_HOST:CONTEXT_BROKER_DASHBOARD_PORT.

On startup, the nearest .env file (walked up from CWD) is loaded into
os.environ — but only for keys that aren't already set by the parent process.
This lets multiple editor MCP clients (Claude Code, Codex, Cursor, ...) point
at the same Redis/dashboard without exporting env vars in every shell, while
still letting per-editor overrides win. Set CONTEXT_BROKER_AUTO_LOAD_ENV=0 to
disable .env discovery entirely.

Transport selection via CONTEXT_BROKER_TRANSPORT env var:
    stdio            - (default) stdin/stdout JSON-RPC
    sse              - Server-Sent Events over HTTP
    streamable-http  - Streamable HTTP transport
    ws               - WebSocket transport
"""

import sys

# Load .env BEFORE importing context_broker.config (which reads env at import time).
from context_broker.env_loader import auto_load_env_enabled, load_env
from context_broker.dashboard_ttc.tools.instance_guard import (
    dashboard_already_running as _dashboard_already_running,
)

if auto_load_env_enabled():
    load_env()

from context_broker.config import (  # noqa: E402
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    HOST,
    PORT,
    TRANSPORT,
)


def _run_dashboard() -> None:
    """Run the web-only cross-chat dashboard, no MCP server attached."""
    if _dashboard_already_running(DASHBOARD_HOST, DASHBOARD_PORT):
        print(
            f"Context Broker dashboard already running on "
            f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT} — leaving it alone.",
            file=sys.stderr,
        )
        return

    import uvicorn

    from context_broker.dashboard import create_app
    from context_broker.server_ttc.tools.auth_tools import assert_bind_allowed

    assert_bind_allowed(DASHBOARD_HOST, DASHBOARD_PORT, "Dashboard")
    app = create_app()
    print(
        f"Starting Context Broker dashboard on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=DASHBOARD_HOST, port=DASHBOARD_PORT, log_level="warning")


def _run_mcp_server() -> None:
    """Run the MCP server using the selected transport."""
    from context_broker.doctor_ttc import startup_warnings
    from context_broker.lifecycle import start_lifecycle_watchdogs
    from context_broker.server import get_default_server
    from context_broker.server_ttc.tools.auth_tools import assert_bind_allowed

    for warning in startup_warnings():
        print(warning, file=sys.stderr)

    if TRANSPORT in ("sse", "streamable-http", "ws"):
        assert_bind_allowed(HOST, PORT, f"MCP {TRANSPORT} transport")

    start_lifecycle_watchdogs()
    mcp = get_default_server()

    if TRANSPORT == "ws":
        import uvicorn
        from context_broker.server_ttc.tools.ws_transport import create_ws_app

        app = create_ws_app(mcp)
        print(
            f"Starting Context Broker MCP (WebSocket) on ws://{HOST}:{PORT}/ws",
            file=sys.stderr,
        )
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    elif TRANSPORT in ("sse", "streamable-http"):
        mcp.run(transport=TRANSPORT, host=HOST, port=PORT)
    else:
        mcp.run(transport="stdio")


def main() -> None:
    """Run the Context Broker MCP server or web dashboard."""
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        _run_dashboard()
        return
    _run_mcp_server()


if __name__ == "__main__":
    main()
