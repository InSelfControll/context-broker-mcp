"""One authenticated local server for all coding-agent sessions."""

import os
import secrets
import socket
from pathlib import Path
from urllib.parse import unquote

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from filelock import FileLock

from context_broker.shared_ttc.tools.runtime_tools import runtime_directory
from context_broker.shared_ttc.tools.scope import PROJECT_HEADER, PROJECT_ROOT


class LocalTokenVerifier(TokenVerifier):
    """Accept only the opaque secret issued to this local service instance."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self.secret = secret

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify without leaking the expected token through timing differences."""
        if secrets.compare_digest(token, self.secret):
            return AccessToken(token=token, client_id="local-agent", scopes=[])
        return None


class ProjectScopeMiddleware(Middleware):
    """Bind every request to its proxy's project; never mutate process CWD or env."""

    async def on_request(self, context, call_next):
        """Require an existing absolute project root for all shared requests."""
        raw = get_http_headers().get(PROJECT_HEADER, "")
        path = Path(unquote(raw))
        if not raw or not path.is_absolute() or not path.is_dir():
            raise ValueError("shared connections require an absolute existing project root")
        token = PROJECT_ROOT.set(str(path.resolve()))
        try:
            return await call_next(context)
        finally:
            PROJECT_ROOT.reset(token)

    async def on_call_tool(self, context, call_next):
        """Supply project identity to handlers that otherwise accept empty roots."""
        from context_broker.project import get_project_name, resolve_project_root

        arguments = dict(context.message.arguments or {})
        root = resolve_project_root(arguments.get("project_root", ""))
        # All project-aware public tools accept project_root. Tool schemas avoid
        # injecting unknown parameters into router/metric tools.
        tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        properties = tool.parameters.get("properties", {})
        if "project_root" in properties:
            arguments["project_root"] = root
        if "project_name" in properties:
            name = get_project_name(root)
            if arguments.get("project_name", name) != name:
                raise ValueError("project_name does not match this connection's project")
            arguments["project_name"] = name
        message = context.message.model_copy(update={"arguments": arguments})
        return await call_next(context.copy(message=message))


def create_shared_server(secret: str):
    """Build the shared server with authentication and request project isolation."""
    from context_broker.server import create_mcp_server

    server = create_mcp_server()
    server.auth = LocalTokenVerifier(secret)
    server.add_middleware(ProjectScopeMiddleware())

    @server.tool()
    def get_memory_usage() -> dict[str, int | bool]:
        """Report this shared process's cache budget and model loading state."""
        from context_broker.indexer_ttc.tools import state

        return dict(
            state.POOL.snapshot(), pid=os.getpid(), model_loaded=state.SHARED_MODEL is not None
        )

    return server


def run_shared_server(port: int = 8771) -> None:
    """Serve until stopped by the user; one owner per runtime directory."""
    from context_broker.lifecycle import start_lifecycle_watchdogs
    from context_broker.storage_ttc.tools.json_tools import atomic_write_json
    from starlette.responses import JSONResponse
    import uvicorn

    directory = runtime_directory()
    with FileLock(str(directory / "server.lock"), timeout=0), socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        port = listener.getsockname()[1]
        secret = secrets.token_urlsafe(48)
        server = create_shared_server(secret)
        runner = None

        @server.custom_route("/health", methods=["GET", "POST"])
        @server.custom_route("/shutdown", methods=["POST"])
        async def control(request):
            if not secrets.compare_digest(
                request.headers.get("authorization", "").encode(), f"Bearer {secret}".encode()
            ):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if request.url.path == "/shutdown":
                runner.should_exit = True
            return JSONResponse({"service": "context-broker"})

        runner = uvicorn.Server(uvicorn.Config(
            server.http_app(path="/mcp"), host="127.0.0.1", port=port,
            log_level="warning", timeout_graceful_shutdown=5,
        ))
        descriptor = directory / "service.json"
        # atomic_write_json uses a private mkstemp file (0600).
        atomic_write_json(descriptor, {"port": port, "token": secret, "pid": os.getpid()})
        try:
            start_lifecycle_watchdogs(shared=True)
            runner.run(sockets=[listener])
        finally:
            descriptor.unlink(missing_ok=True)
