"""Keep transport-level task failures consistent with their structured status."""

from fastmcp.tools import ToolResult
from mcp.types import CallToolResult


class TaskResult(ToolResult):
    """Failed task payloads must also set the MCP protocol's error flag."""

    def to_mcp_result(self) -> CallToolResult:
        """Preserve structured diagnostics and completed handoffs in error responses."""
        return CallToolResult(
            content=self.content,
            structuredContent=self.structured_content,
            isError=(self.structured_content or {}).get("status") == "failed",
        )
