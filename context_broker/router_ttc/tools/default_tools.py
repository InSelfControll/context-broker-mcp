"""Default tool descriptors shipped by Context Broker."""

from __future__ import annotations

from context_broker.router_ttc.tools.registry_tools import ToolDescriptor


def default_tool_descriptors() -> list[ToolDescriptor]:
    """Return descriptors for the built-in MCP tools.

    The router remains client-agnostic: clients can use these recommendations to
    decide which MCP tools to expose, and future integrations can merge in their
    own descriptor catalogs before routing.
    """
    return [
        ToolDescriptor(
            id="search_codebase_tool",
            name="search_codebase_tool",
            category="search",
            description="Semantic codebase search for relevant source files and snippets.",
            schema_summary="query: str, project_root: str = ''",
            tags=["search", "code", "semantic", "context"],
            permissions=["read_project_files"],
            risk_level="low",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="find_in_codebase",
            name="find_in_codebase",
            category="search",
            description=(
                "Local literal/regex pattern search in codebase files. "
                "Returns exact matches with line numbers and snippets. "
                "No external LLM — completes locally to save tokens."
            ),
            schema_summary="pattern: str, project_root: str, case_sensitive: bool, use_regex: bool, file_glob: str",
            tags=["search", "code", "literal", "grep", "regex", "local", "exact"],
            permissions=["read_project_files"],
            risk_level="low",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="auto_search",
            name="auto_search",
            category="search",
            description="Automatically retrieve entry points, setup, and architecture context.",
            schema_summary="project_root: str = ''",
            tags=["search", "architecture", "setup", "context"],
            permissions=["read_project_files"],
            risk_level="low",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="token_counter",
            name="token_counter",
            category="metrics",
            description="Return latest token usage and savings report.",
            schema_summary="project_root: str = ''",
            tags=["token", "tokens", "metrics", "savings"],
            permissions=["read_token_reports"],
            risk_level="low",
            file_capable=False,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="token_history",
            name="token_history",
            category="metrics",
            description="Show graph-ready token savings history across requests.",
            schema_summary="project_root: str = '', limit: int = 20",
            tags=["token", "tokens", "history", "metrics"],
            permissions=["read_token_reports"],
            risk_level="low",
            file_capable=False,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="save_search_results",
            name="save_search_results",
            category="storage",
            description="Search codebase and persist relevant results to JSON.",
            schema_summary="query: str, filename: str, project_root: str, subdir: str, top_k: int",
            tags=["search", "storage", "json", "cache"],
            permissions=["read_project_files", "write_context_broker_storage"],
            risk_level="medium",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="load_saved_results",
            name="load_saved_results",
            category="storage",
            description="Load previously saved JSON search results.",
            schema_summary="project_name: str, filename: str, subdir: str, project_root: str",
            tags=["storage", "json", "cache", "load"],
            permissions=["read_context_broker_storage"],
            risk_level="low",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="record_turn",
            name="record_turn",
            category="context",
            description="Persist one chat exchange to local ledger and optional cross-chat backend.",
            schema_summary="session_id: str, user_message: str, assistant_message: str, project_root: str",
            tags=["chat", "context", "memory", "redis", "honcho"],
            permissions=["write_chat_context"],
            risk_level="medium",
            file_capable=True,
            network_capable=True,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="load_chat_context",
            name="load_chat_context",
            category="context",
            description="Load relevant persisted chat context from local, Honcho, or Redis backend.",
            schema_summary="session_id: str, tokens: int, search_query: str, project_root: str",
            tags=["chat", "context", "redis", "honcho"],
            permissions=["read_chat_context"],
            risk_level="low",
            file_capable=True,
            network_capable=True,
            shell_capable=False,
        ),
        ToolDescriptor(
            id="ensure_changelog_tool",
            name="ensure_changelog_tool",
            category="docs",
            description="Create or update CHANGELOG.md from git history.",
            schema_summary="project_root: str = ''",
            tags=["docs", "changelog", "git"],
            permissions=["write_project_files"],
            risk_level="medium",
            file_capable=True,
            network_capable=False,
            shell_capable=False,
        ),
    ]
