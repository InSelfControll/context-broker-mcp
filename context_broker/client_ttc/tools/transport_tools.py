"""Transport adapters for downstream MCP client sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from typing import Any

from context_broker.client_ttc.tools.contract_tools import (
    DownstreamServerConfig,
    DownstreamTransport,
)

_SAFE_ENV_KEYS = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "TMPDIR"}


def filtered_stdio_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a safe environment for stdio MCP subprocesses.

    Secrets from the parent process are not inherited unless explicitly supplied
    by the server config. XDG variables are kept because many CLIs need them for
    cache/config directory discovery.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _SAFE_ENV_KEYS or key.startswith("XDG_")
    }
    env.update(extra_env or {})
    return env


@asynccontextmanager
async def open_downstream_session(config: DownstreamServerConfig) -> AsyncIterator[Any]:
    """Open an initialized MCP client session for a downstream server.

    The import is intentionally lazy so the package can still load in contexts
    where the MCP SDK is unavailable; the connection attempt then raises a clear
    runtime error instead of breaking unrelated server functionality.
    """
    config.validate()
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
        raise RuntimeError("mcp SDK is required for downstream MCP client connections") from exc

    if config.transport == DownstreamTransport.STDIO:
        params = StdioServerParameters(
            command=config.command or "",
            args=config.args,
            env=filtered_stdio_env(config.env),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    if config.transport == DownstreamTransport.HTTP:
        async with streamablehttp_client(
            config.url or "",
            headers=config.headers,
            timeout=config.timeout_seconds,
        ) as streams:
            read_stream, write_stream, _get_session_id = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    if config.transport == DownstreamTransport.SSE:
        async with sse_client(
            config.url or "",
            headers=config.headers,
            timeout=config.timeout_seconds,
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return

    raise ValueError(f"unsupported downstream transport: {config.transport}")
