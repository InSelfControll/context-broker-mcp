"""
Context Broker - Simple CLI Entry Point

A simple entry point for running the Context Broker MCP server.
For full functionality, use context-broker.py directly.
"""

from context_broker.server import get_default_server


def main():
    """Run the Context Broker MCP server."""
    print("🚀 Starting Context Broker MCP Server...")
    print("For help, see: README.md")
    print("")
    
    mcp = get_default_server()
    mcp.run()


if __name__ == "__main__":
    main()
