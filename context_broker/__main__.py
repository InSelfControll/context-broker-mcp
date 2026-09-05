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

import os
import sys

# Load .env BEFORE importing context_broker.config (which reads env at import time).
from context_broker.env_loader import load_env

if os.getenv("CONTEXT_BROKER_AUTO_LOAD_ENV", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}:
    load_env()

from context_broker.config import (  # noqa: E402
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    HOST,
    PORT,
    TRANSPORT,
)


def _dashboard_already_running(host: str, port: int) -> bool:
    """Return True if a Context Broker dashboard is already serving on host:port."""
    import json
    import urllib.error
    import urllib.request

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{probe_host}:{port}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            if resp.status != 200:
                return False
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        return False
    except Exception:
        return False
    # Our /api/status always includes a "backend" field. Anything else on the
    # port is not us — let uvicorn fail loudly instead of silently no-op'ing.
    return isinstance(body, dict) and "backend" in body


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

    app = create_app()
    print(
        f"Starting Context Broker dashboard on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=DASHBOARD_HOST, port=DASHBOARD_PORT, log_level="warning")


def _run_mcp_server() -> None:
    """Run the MCP server using the selected transport."""
    from context_broker.lifecycle import start_lifecycle_watchdogs
    from context_broker.server import get_default_server

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
    """Parse commands before starting any server or loading service dependencies."""
    import argparse

    from context_broker.integrations_ttc.tools.config_tools import HOSTS

    parser = argparse.ArgumentParser(
        prog="context-broker",
        description="Project-scoped context and history for coding agents. "
        "With no command, start the stdio MCP server (or configured transport).",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("mcp", help="Start the MCP server using the configured transport")
    commands.add_parser("dashboard", help="Open the web dashboard service")
    serve = commands.add_parser("serve", help="Run one shared model and memory pool")
    serve.add_argument("--port", type=int, default=8771)
    connect = commands.add_parser("connect", help="Connect an agent to a project's shared service")
    connect.add_argument("--project-root", required=True)
    config = commands.add_parser("integration-config", help="Install Context Broker into native coding-agent config")
    config.add_argument("--host", required=True, choices=HOSTS)
    config.add_argument("--project-root", required=True)
    config.add_argument("--runtime-dir", default="")
    config.add_argument("--config-path", default="", help="Override destination (for profiles)")
    config.add_argument("--print", dest="print_only", action="store_true", help="Print config without writing")
    args = parser.parse_args()
    if args.command == "integration-config":
        from context_broker.integrations_ttc.tools.config_tools import client_config

        if args.print_only:
            sys.stdout.write(client_config(args.host, args.project_root, runtime_dir=args.runtime_dir))
        else:
            from context_broker.integrations_ttc.tools.install_tools import install_config
            try:
                result = install_config(args.host, args.project_root, runtime_dir=args.runtime_dir,
                                        config_path=args.config_path)
            except Exception as exc:
                config.exit(1, f"Configuration update failed ({type(exc).__name__}); "
                            "check the destination's format and permissions.\n")
            sys.stdout.write(f"{result['status']}: {result['config_path']}\n")
            if result.get("backup_path"):
                sys.stdout.write(f"Backup: {result['backup_path']}\n")
            sys.stdout.write("Start context-broker serve if needed, then restart your agent.\n")
    elif args.command == "serve":
        if not 0 < args.port < 65536:
            serve.error("port must be between 1 and 65535")
        from context_broker.shared_ttc.tasks.service_tasks import run_shared_server

        run_shared_server(args.port)
    elif args.command == "connect":
        from context_broker.shared_ttc.tasks.proxy_tasks import run_agent_proxy

        run_agent_proxy(args.project_root)
    elif args.command == "dashboard":
        _run_dashboard()
    else:
        _run_mcp_server()


if __name__ == "__main__":
    main()
