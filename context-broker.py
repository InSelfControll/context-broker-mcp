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
    CONTEXT_BROKER_ENABLE_PROGRESS_NOTIFICATIONS - Enable per-call MCP progress updates
    CONTEXT_BROKER_LOCAL_ONLY - Prefer cached models; bootstrap-download missing models
    CONTEXT_BROKER_AUTO_LOAD_ENV - Load the nearest .env file (default: enabled)
    CONTEXT_BROKER_TRANSPORT - Transport: stdio, sse, streamable-http, or ws
    CONTEXT_BROKER_HOST - Host for network transports (default: all interfaces)
    CONTEXT_BROKER_PORT - Port for network transports (default: 8765)
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from context_broker.__main__ import main

if __name__ == "__main__":
    main()
