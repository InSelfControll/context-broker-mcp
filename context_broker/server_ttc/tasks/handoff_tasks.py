"""Expose lossless project memory checkpoints for model switches."""

from fastmcp import FastMCP

from context_broker.context_ttc.tasks.handoff_tasks import load_handoff, save_handoff
from context_broker.delegation_ttc.tools.failure_tools import exception_reason, failure
from context_broker.lifecycle import tracked_activity
from context_broker.server_ttc.tools.blocking import run_blocking
from context_broker.server_ttc.tools.task_result import TaskResult


async def _invoke(operation, **kwargs) -> TaskResult:
    with tracked_activity():
        try:
            result = await run_blocking(operation, **kwargs)
        except (ValueError, OSError) as exc:
            result = failure(exception_reason(exc), code="handoff_failed")
        return TaskResult(structured_content=result)


def register_handoff_tools(mcp: FastMCP) -> None:
    """Register model-neutral save/load tools on both public server surfaces."""

    @mcp.tool()
    async def save_model_handoff(
        source_model: str, session_id: str, state: dict, files: list[str], project_root: str = ""
    ) -> TaskResult:
        """Save before switching models. Pass exact messages and all known project state.

        State requires goal, messages (string-valued objects), decisions, constraints,
        facts, tasks, acceptance_criteria, and open_questions. Each task has task/status,
        failure_reason if failed, and evidence if completed. Include relevant file paths.
        Give the returned handoff_id to the next model. Existing snapshots are immutable.
        """
        return await _invoke(
            save_handoff,
            project_root=project_root,
            source_model=source_model,
            session_id=session_id,
            state=state,
            files=files,
        )

    @mcp.tool()
    async def load_model_handoff(
        handoff_id: str, target_model: str, max_bytes: int = 32_000, project_root: str = ""
    ) -> TaskResult:
        """Load saved context before the new model continues. Never silently trims memory.

        Choose a byte budget fitting the host's output/context limits. A stale checkpoint
        or insufficient budget returns failed; recover context before continuing work.
        This restores supplied memory, not a model's private reasoning or unsaved history.
        """
        return await _invoke(
            load_handoff,
            project_root=project_root,
            handoff_id=handoff_id,
            target_model=target_model,
            max_bytes=max_bytes,
        )
