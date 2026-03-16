"""
WebSocket transport for the MCP server.

Bridges WebSocket connections to the MCP low-level server using
anyio memory object streams, following the same pattern as the
built-in stdio transport.

Usage:
    mcp = get_default_server()
    mcp.run(transport="ws", host="0.0.0.0", port=8765)

    # Or via environment variables:
    CONTEXT_BROKER_TRANSPORT=ws
    CONTEXT_BROKER_HOST=0.0.0.0
    CONTEXT_BROKER_PORT=8765
"""

import sys
from contextlib import asynccontextmanager

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

import mcp.types as types
from mcp.shared.message import SessionMessage


@asynccontextmanager
async def websocket_server(ws: WebSocket):
    """
    Server transport for a single WebSocket connection.

    Creates paired memory streams that bridge WebSocket text frames
    to the MCP JSON-RPC message format expected by Server.run().

    Follows the same pattern as mcp.server.stdio.stdio_server.
    """
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]

    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async def ws_reader():
        """Read JSON-RPC messages from WebSocket and push to MCP read stream."""
        try:
            async with read_stream_writer:
                while True:
                    try:
                        data = await ws.receive_text()
                    except WebSocketDisconnect:
                        break
                    try:
                        message = types.JSONRPCMessage.model_validate_json(data)
                    except Exception as exc:
                        await read_stream_writer.send(exc)
                        continue
                    await read_stream_writer.send(SessionMessage(message))
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def ws_writer():
        """Read MCP responses from write stream and send over WebSocket."""
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    json_str = session_message.message.model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                    await ws.send_text(json_str)
        except (anyio.ClosedResourceError, WebSocketDisconnect):
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as tg:
        tg.start_soon(ws_reader)
        tg.start_soon(ws_writer)
        yield read_stream, write_stream


def create_ws_app(server) -> Starlette:
    """
    Create a Starlette ASGI app with a WebSocket endpoint for MCP.

    Each WebSocket connection gets its own MCP session, allowing
    multiple concurrent clients.

    Args:
        server: The FastMCP server instance.
    """
    from mcp.server.lowlevel.server import NotificationOptions

    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        print(
            f"[ws] client connected: {ws.client}",
            file=sys.stderr,
        )
        try:
            async with websocket_server(ws) as (read_stream, write_stream):
                await server._mcp_server.run(
                    read_stream,
                    write_stream,
                    server._mcp_server.create_initialization_options(
                        notification_options=NotificationOptions(
                            tools_changed=True,
                        ),
                    ),
                )
        except WebSocketDisconnect:
            pass
        finally:
            print(
                f"[ws] client disconnected: {ws.client}",
                file=sys.stderr,
            )

    return Starlette(
        routes=[WebSocketRoute("/ws", ws_endpoint)],
    )
