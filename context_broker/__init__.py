"""
Context Broker MCP Server - Semantic Code Search

A Model Context Protocol (MCP) server that provides semantic search capabilities
for codebases using sentence transformers.
"""

__version__ = "0.1.0"
__author__ = "Context Broker Team"

def __getattr__(name: str):
    """Keep lightweight CLI clients from importing the server's ML runtime."""
    if name == "create_mcp_server":
        from context_broker.server import create_mcp_server

        return create_mcp_server
    raise AttributeError(name)

__all__ = ["create_mcp_server"]
