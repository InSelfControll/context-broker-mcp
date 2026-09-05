"""Conservative delegation suggestions; a suggestion never authorizes execution."""


def delegation_offer(task: str) -> dict | None:
    """Surface the opt-in workflow for explicitly large or parallel task requests."""
    lowered = task.lower()
    signals = (
        "large task",
        "big task",
        "complex task",
        "multi-agent",
        "multiple agents",
        "parallel agents",
        "split this task",
    )
    if not any(signal in lowered for signal in signals) and len(task) < 1500:
        return None
    return {
        "tool": "delegate_large_task",
        "requires_user_choice": True,
        "question": "Would you like to split this task between agents or keep one agent?",
        "model_required": True,
        "instructions": "Only propose independent assignments. Preserve the original task, "
        "conversation decisions, project context, and acceptance criteria. "
        "Ask for the exact model if unspecified. The tool obtains consent; "
        "a routing recommendation alone must never launch agents.",
    }
