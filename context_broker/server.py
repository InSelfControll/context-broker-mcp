"""
MCP Server Module

Implements the Model Context Protocol server with tools and resources.
This module defines the interface between the AI and the codebase search functionality.
"""

import os
from typing import Any

from fastmcp import FastMCP

from context_broker.config import StorageMode, STORAGE_MODE, DEFAULT_QUERY
from context_broker.indexer import search_codebase, get_index_for_project
from context_broker.project import resolve_project_root, get_project_name
from context_broker.storage import (
    save_json_data, load_json_data, list_saved_json, get_storage_config_info
)
from context_broker.utils import log


def create_mcp_server() -> FastMCP:
    """
    Create and configure the MCP server.
    
    Returns:
        Configured FastMCP instance
    """
    mcp = FastMCP("Context Broker - Semantic Code Search")
    
    # =============================================================================
    # TOOLS
    # =============================================================================
    
    @mcp.tool()
    def search_codebase_tool(query: str, project_root: str = "") -> str:
        """
        Search the codebase using semantic similarity.
        
        This tool finds relevant files by understanding the meaning of your query
        and matching it against the content of files in the project.
        
        Args:
            query: Natural language search query describing what you're looking for.
                   Examples: "authentication middleware", "database connection setup",
                   "user model definition", "API route handlers"
            project_root: Project root path (optional - auto-detected if not provided)
            
        Returns:
            Formatted string with relevant file contents and token statistics
        """
        root = resolve_project_root(project_root)
        
        try:
            result = search_codebase(query, root, top_k=5)
            
            # Format results with token statistics
            lines = [
                f"🔍 Search Results for: '{result['query']}'",
                f"📁 Project: {result['project']}",
                f"📊 Found {result['returned_files']} relevant files (out of {result['total_files']} total)",
                "",
                "📈 Token Efficiency Report:",
                f"   • Total Project Tokens: {result['total_tokens']:,}",
                f"   • Context Sent: {result['context_tokens']:,}",
                f"   • Tokens Saved: {result['saved_tokens']:,} ({result['saved_percent']:.1f}%)",
                "",
                "=" * 60,
                "",
            ]
            
            for item in result["results"]:
                lines.append(f"### FILE: {item['path']}")
                lines.append(item['content'])
                lines.append("")
            
            return "\n".join(lines)
            
        except Exception as e:
            log(f"❌ Search error: {e}", "ERROR")
            return f"Error: {str(e)}"
    
    @mcp.tool()
    def auto_search(project_root: str = "") -> str:
        """
        Automatically search codebase for main entry points, configuration, and setup.
        
        This is useful for getting initial context about a project when you first
        start working with it. It searches for common patterns like:
        - Main entry points (main.py, index.js, etc.)
        - Configuration files
        - Architecture and setup patterns
        
        Args:
            project_root: Project root path (optional - auto-detected if not provided)
            
        Returns:
            Formatted string with relevant files for understanding the project
        """
        root = resolve_project_root(project_root)
        
        try:
            result = search_codebase(
                "main entry point configuration setup architecture",
                root,
                top_k=5
            )
            
            lines = [
                f"🚀 Auto-Context for Project: {result['project']}",
                f"📊 Found {result['returned_files']} relevant files",
                "",
                "📈 Token Efficiency Report:",
                f"   • Total Project Tokens: {result['total_tokens']:,}",
                f"   • Context Sent: {result['context_tokens']:,}",
                f"   • Tokens Saved: {result['saved_tokens']:,} ({result['saved_percent']:.1f}%)",
                "",
                "=" * 60,
                "",
            ]
            
            for item in result["results"]:
                lines.append(f"### FILE: {item['path']}")
                lines.append(item['content'])
                lines.append("")
            
            return "\n".join(lines)
            
        except Exception as e:
            log(f"❌ Auto-search error: {e}", "ERROR")
            return f"Error: {str(e)}"
    
    @mcp.tool()
    def save_search_results(
        query: str = "",
        filename: str = "",
        project_root: str = "",
        subdir: str = "",
        top_k: int = 5
    ) -> str:
        """
        Search the codebase and save results to a JSON file.
        
        This allows you to persist search results for later reference.
        Files are organized by project and can be stored in subdirectories.
        
        Storage location depends on CONTEXT_BROKER_STORAGE_MODE environment variable:
        - "global" (default): ~/.context-broker/{project-name}/{subdir}/
        - "in-project": {project-root}/.context-broker/{subdir}/
        - "both": Saves to local project, checks local first when loading
        
        Args:
            query: Search query describing what you're looking for
            filename: Name for the JSON file (e.g., "auth-middleware.json")
            project_root: Project root path (auto-detected if empty)
            subdir: Optional subdirectory (e.g., "api", "config", "auth")
            top_k: Number of results to include (default: 5)
            
        Returns:
            Path to the saved file
            
        Example:
            save_search_results(
                query="authentication middleware",
                filename="auth-middleware.json",
                subdir="api"
            )
            # Saves to: ~/.context-broker/my-project/api/auth-middleware.json
        """
        if not query:
            return "❌ Error: query is required"
        if not filename:
            return "❌ Error: filename is required"
        
        root = resolve_project_root(project_root)
        project_name = get_project_name(root)
        
        try:
            # Perform search
            result = search_codebase(query, root, top_k)
            
            # Create save data structure
            data = {
                "project": project_name,
                "project_root": root,
                "query": query,
                "storage_mode": STORAGE_MODE,
                "top_k": top_k,
                "timestamp": str(os.times().system),
                "file_count": len(result["results"]),
                "files": [
                    {
                        "path": item["path"],
                        "content": item["content"],
                    }
                    for item in result["results"]
                ],
                "statistics": {
                    "total_tokens": result["total_tokens"],
                    "context_tokens": result["context_tokens"],
                    "saved_tokens": result["saved_tokens"],
                    "saved_percent": result["saved_percent"],
                }
            }
            
            # Save to storage
            filepath = save_json_data(
                project_name, filename, data, subdir, root
            )
            
            return f"✅ Saved {len(result['results'])} files to: {filepath}"
            
        except Exception as e:
            log(f"❌ Save error: {e}", "ERROR")
            return f"❌ Error saving results: {str(e)}"
    
    @mcp.tool()
    def list_saved_results(
        project_name: str,
        subdir: str = "",
        project_root: str = ""
    ) -> str:
        """
        List all saved JSON results for a project.
        
        Args:
            project_name: Name of the project
            subdir: Optional subdirectory to list
            project_root: Required for in-project storage mode
            
        Returns:
            Formatted list of saved files with storage locations
        """
        if not project_name:
            return "❌ Error: project_name is required"
        
        try:
            files = list_saved_json(project_name, subdir, project_root)
            
            if not files:
                subdir_msg = f" in '{subdir}'" if subdir else ""
                return f"📭 No saved results found for project '{project_name}'{subdir_msg}."
            
            lines = [
                f"📁 Saved Results for: {project_name}",
                f"📦 Storage Mode: {STORAGE_MODE}",
                "",
            ]
            
            for filename in files:
                lines.append(f"  📄 {filename}")
            
            lines.append("")
            lines.append(f"Total: {len(files)} files")
            
            return "\n".join(lines)
            
        except Exception as e:
            log(f"❌ List error: {e}", "ERROR")
            return f"❌ Error listing results: {str(e)}"
    
    @mcp.tool()
    def load_saved_results(
        project_name: str,
        filename: str,
        subdir: str = "",
        project_root: str = ""
    ) -> str:
        """
        Load previously saved search results.
        
        In "both" storage mode, checks local project first, then global.
        
        Args:
            project_name: Name of the project
            filename: Name of the saved JSON file
            subdir: Optional subdirectory
            project_root: Required for in-project storage mode
            
        Returns:
            The saved search results with file contents
        """
        if not project_name:
            return "❌ Error: project_name is required"
        if not filename:
            return "❌ Error: filename is required"
        
        try:
            data = load_json_data(project_name, filename, subdir, project_root)
            
            if data is None:
                hint = ""
                if STORAGE_MODE == StorageMode.IN_PROJECT and not project_root:
                    hint = "\n💡 Hint: In 'in-project' mode, you need to provide project_root"
                return f"❌ File not found: {filename}{hint}"
            
            # Format the results with statistics
            stats = data.get('statistics', {})
            lines = [
                f"📋 Saved Search Results",
                f"Project: {data.get('project', 'unknown')}",
                f"Query: {data.get('query', 'unknown')}",
                f"Storage Mode: {data.get('storage_mode', 'unknown')}",
                f"Files: {data.get('file_count', 0)}",
                "",
            ]
            
            if stats:
                lines.extend([
                    "📈 Token Efficiency Report (at time of saving):",
                    f"   • Total Project Tokens: {stats.get('total_tokens', 0):,}",
                    f"   • Context Sent: {stats.get('context_tokens', 0):,}",
                    f"   • Tokens Saved: {stats.get('saved_tokens', 0):,} ({stats.get('saved_percent', 0):.1f}%)",
                    "",
                ])
            
            lines.extend([
                "=" * 50,
                "",
            ])
            
            for file_info in data.get("files", []):
                lines.append(f"### FILE: {file_info['path']}")
                lines.append(file_info.get("content", ""))
                lines.append("")
            
            return "\n".join(lines)
            
        except Exception as e:
            log(f"❌ Load error: {e}", "ERROR")
            return f"❌ Error loading results: {str(e)}"
    
    @mcp.tool()
    def get_storage_config() -> str:
        """
        Get the current storage configuration.
        
        Shows storage mode, base directory, and folder structure.
        
        Returns:
            Current storage configuration details
        """
        config = get_storage_config_info()
        
        lines = [
            "📦 Context Broker Storage Configuration",
            "",
            f"Current Mode: {config['mode']}",
            "",
            "Available Modes:",
        ]
        
        for mode, description in config['modes'].items():
            marker = " ✅ DEFAULT" if mode == config['mode'] else ""
            lines.append(f"  • '{mode}' - {description}{marker}")
        
        lines.extend([
            "",
            f"Base Directory (global): {config['base_dir']}",
            f"In-Project Folder Name: {config['in_project_folder']}",
            "",
            "Environment Variables:",
        ])
        
        for var, desc in config['environment_variables'].items():
            lines.append(f"  {var}")
            lines.append(f"    {desc}")
        
        return "\n".join(lines)
    
    # =============================================================================
    # RESOURCES
    # =============================================================================
    
    @mcp.resource("codebase://auto-context")
    def auto_context_resource() -> str:
        """
        Automatically provides codebase context on every request.
        
        This resource is automatically fetched by MCP clients on every request,
        providing relevant context without explicit tool calls.
        
        Returns:
            Relevant files for understanding the current project
        """
        root = resolve_project_root()
        
        try:
            result = search_codebase(DEFAULT_QUERY, root, top_k=3)
            
            lines = [
                f"🔄 Auto-Context: {result['project']}",
                "",
                "📈 Token Efficiency Report:",
                f"   • Total Project Tokens: {result['total_tokens']:,}",
                f"   • Context Sent: {result['context_tokens']:,}",
                f"   • Tokens Saved: {result['saved_tokens']:,} ({result['saved_percent']:.1f}%)",
                "",
            ]
            
            for item in result["results"]:
                lines.append(f"### FILE: {item['path']}")
                lines.append(item['content'])
                lines.append("")
            
            return "\n".join(lines)
            
        except Exception as e:
            # Return empty string on error to not break the flow
            return f""
    
    # =============================================================================
    # PROMPTS
    # =============================================================================
    
    @mcp.prompt("auto-search")
    def auto_search_prompt() -> str:
        """
        System instruction to always search the codebase first.
        
        This prompt instructs the AI to use search tools before answering
        questions about code.
        """
        return """IMPORTANT: Before answering ANY user request about code, you MUST first call the `search_codebase` tool with:
- query: Extract the main topic/keywords from the user's request
- project_root: Optional - will be auto-detected from current directory

Alternatively, use `auto_search` tool for initial project exploration (no arguments needed).

This ensures you have relevant codebase context before responding. Never skip this step."""
    
    return mcp


# Global server instance for backward compatibility
_default_server: Any = None


def get_default_server() -> FastMCP:
    """Get or create the default MCP server instance."""
    global _default_server
    if _default_server is None:
        _default_server = create_mcp_server()
    return _default_server
