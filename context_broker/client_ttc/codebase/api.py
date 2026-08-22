"""Public API for downstream MCP client support."""

from context_broker.client_ttc.tasks.connection_tasks import (
    DownstreamConnectionManager,
    ManagedDownstreamConnection,
    managed_downstream_manager,
)
from context_broker.client_ttc.tools.contract_tools import (
    ConnectionState,
    DownstreamCallResult,
    DownstreamCapabilities,
    DownstreamPrompt,
    DownstreamResource,
    DownstreamServerConfig,
    DownstreamTool,
    DownstreamTransport,
)
from context_broker.client_ttc.tools.environment_tools import filtered_stdio_env
from context_broker.client_ttc.tools.transport_tools import open_downstream_session

__all__ = [
    "ConnectionState",
    "DownstreamCallResult",
    "DownstreamCapabilities",
    "DownstreamConnectionManager",
    "DownstreamPrompt",
    "DownstreamResource",
    "DownstreamServerConfig",
    "DownstreamTool",
    "DownstreamTransport",
    "ManagedDownstreamConnection",
    "filtered_stdio_env",
    "managed_downstream_manager",
    "open_downstream_session",
]
