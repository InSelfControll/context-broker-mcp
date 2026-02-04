#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "sentence-transformers",
#   "scikit-learn",
#   "numpy",
#   "torch",
#   "tiktoken"
# ]
# ///
"""
Context Broker MCP Server - Main Entry Point

This is the main entry point for the Context Broker MCP server.
It can be run directly or imported as a module.

For modular imports, use:
    from context_broker.server import create_mcp_server
    mcp = create_mcp_server()

Usage:
    python context-broker.py
    
Environment Variables:
    CONTEXT_BROKER_PROJECT_ROOT - Default project root path
    CONTEXT_BROKER_STORAGE_MODE - Storage mode: global, in-project, or both
    CONTEXT_BROKER_STORAGE_DIR - Base directory for global storage
    CONTEXT_BROKER_DEFAULT_QUERY - Default query for auto-context
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from context_broker.server import get_default_server

if __name__ == "__main__":
    mcp = get_default_server()
    mcp.run()
