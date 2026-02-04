"""
Context Broker MCP Server - Semantic Code Search

A Model Context Protocol (MCP) server that provides semantic search capabilities
for codebases using sentence transformers.
"""

__version__ = "0.1.0"
__author__ = "Context Broker Team"

from context_broker.server import create_mcp_server

__all__ = ["create_mcp_server"]
