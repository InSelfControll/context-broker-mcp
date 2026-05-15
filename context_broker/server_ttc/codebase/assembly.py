"""Server assembly layer (Codebase in TTC pattern)."""

from fastmcp import FastMCP

from context_broker.server_ttc.codebase.resources import register_resources_and_prompts
from context_broker.server_ttc.tasks.agents_tasks import register_agents_tools
from context_broker.server_ttc.tasks.changelog_tasks import register_changelog_tools
from context_broker.server_ttc.tasks.context_tasks import register_context_tools
from context_broker.server_ttc.tasks.docs_tasks import register_docs_tools
from context_broker.server_ttc.tasks.search_tasks import register_search_tools
from context_broker.server_ttc.tasks.storage_tasks import register_storage_tools
from context_broker.server_ttc.tasks.token_tasks import register_token_tools

_default_server: FastMCP | None = None


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server."""
    mcp = FastMCP("Context Broker - Semantic Code Search")
    register_search_tools(mcp)
    register_storage_tools(mcp)
    register_token_tools(mcp)
    register_context_tools(mcp)
    register_agents_tools(mcp)
    register_changelog_tools(mcp)
    register_docs_tools(mcp)
    register_resources_and_prompts(mcp)
    return mcp


def get_default_server() -> FastMCP:
    """Get or create default server instance."""
    global _default_server
    if _default_server is None:
        _default_server = create_mcp_server()
    return _default_server
