"""Token-budget calculations for the token-slim router."""

from __future__ import annotations

from typing import Any

from context_broker.indexer_ttc.tools.model_tools import get_encoder
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor
from context_broker.utils import count_tokens


def descriptor_token_count(descriptor: ToolDescriptor) -> int:
    """Estimate tokens needed to expose one descriptor."""
    encoder = get_encoder()
    payload = descriptor.to_public_dict()
    return count_tokens(str(payload), encoder)


def token_report_for_selection(
    all_tools: list[ToolDescriptor], selected_tools: list[ToolDescriptor], token_budget: int
) -> dict[str, Any]:
    """Return token budget and savings metrics for a selected tool slice."""
    total_tokens = sum(descriptor_token_count(tool) for tool in all_tools)
    exposed_tokens = sum(descriptor_token_count(tool) for tool in selected_tools)
    saved_tokens = max(total_tokens - exposed_tokens, 0)
    saved_percent = (saved_tokens / total_tokens * 100.0) if total_tokens else 0.0
    return {
        "total_tools": len(all_tools),
        "exposed_tools": len(selected_tools),
        "hidden_tools": max(len(all_tools) - len(selected_tools), 0),
        "total_tool_tokens": total_tokens,
        "exposed_tool_tokens": exposed_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "token_budget": token_budget,
        "within_budget": exposed_tokens <= token_budget,
    }
