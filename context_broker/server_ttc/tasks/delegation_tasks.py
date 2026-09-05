"""Expose consent-gated multi-agent work through the standard MCP interface."""

from fastmcp import Context, FastMCP

from context_broker.delegation_ttc.tasks.delegation_tasks import DelegationRuntime
from context_broker.lifecycle import tracked_activity


def register_delegation_tools(mcp: FastMCP) -> None:
    """Keep batch admission scoped to this server instance."""
    runtime = DelegationRuntime()

    @mcp.tool()
    async def delegate_large_task(
        task: str,
        model: str,
        subtasks: list[str],
        context: str,
        acceptance_criteria: list[str],
        files: list[str],
        project_root: str = "",
        ctx: Context = None,
    ) -> dict:
        """Offer to split a large task into 2–4 independent agents, then review the results.

        Call only for a large task with a user-specified exact model. Include the original
        goal, conversation decisions, constraints, relevant files, and acceptance criteria.
        This tool asks the user whether to split BEFORE starting agents. Decline/cancel or
        unavailable elicitation starts no agents. Workers return proposals; the host must
        integrate and execute verification before claiming completion. Never split
        dependent work or drop context to fit the input limit.
        """
        with tracked_activity():
            return await runtime.run(
                task=task,
                model=model,
                subtasks=subtasks,
                context=context,
                acceptance_criteria=acceptance_criteria,
                files=files,
                project_root=project_root,
                ctx=ctx,
            )
