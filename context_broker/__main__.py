"""
Entry point for running as a module: python -m context_broker
"""

from context_broker.server import get_default_server


def main():
    """Run the Context Broker MCP server."""
    mcp = get_default_server()
    mcp.run()


if __name__ == "__main__":
    main()
