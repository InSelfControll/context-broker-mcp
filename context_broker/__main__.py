"""
Entry point for running as a module: python -m context_broker

Transport selection via CONTEXT_BROKER_TRANSPORT env var:
    stdio            - (default) stdin/stdout JSON-RPC
    sse              - Server-Sent Events over HTTP
    streamable-http  - Streamable HTTP transport
    ws               - WebSocket transport
"""

import sys

from context_broker.config import HOST, PORT, TRANSPORT
from context_broker.server import get_default_server


def main():
    """Run the Context Broker MCP server."""
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
        # Default: stdio
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
