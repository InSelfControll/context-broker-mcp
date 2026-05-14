"""
Starlette app for the web-only cross-chat dashboard.

Routes:
  GET /                                            project list (HTML)
  GET /projects/{digest}                           session list for a project (HTML)
  GET /projects/{digest}/sessions/{session_id}     message viewer (HTML)
  GET /api/projects                                JSON list of projects
  GET /api/projects/{digest}/sessions              JSON list of sessions
  GET /api/projects/{digest}/sessions/{session_id} JSON dump of one session
  GET /api/status                                  JSON backend status
"""

from typing import Any

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from context_broker.dashboard_ttc.tasks import data_tasks
from context_broker.dashboard_ttc.tools.templates import (
    render_messages_page,
    render_project_page,
    render_projects_page,
    render_user_activity_page,
    render_users_page,
)


def _json_error(exc: Exception, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=status_code)


def _backend_banner() -> dict[str, Any]:
    return {"backend": data_tasks.active_backend()}


async def index(_: Request) -> HTMLResponse:
    """Render the project list."""
    try:
        projects = data_tasks.list_projects()
    except data_tasks.DashboardError as e:
        return HTMLResponse(render_projects_page([], backend=data_tasks.active_backend(), error=str(e)))
    return HTMLResponse(render_projects_page(projects, backend=data_tasks.active_backend()))


async def project_page(request: Request) -> HTMLResponse:
    digest = request.path_params["digest"]
    try:
        sessions = data_tasks.list_sessions(digest)
    except data_tasks.DashboardError as e:
        raise HTTPException(400, detail=str(e)) from e
    return HTMLResponse(render_project_page(digest, sessions, backend=data_tasks.active_backend()))


async def session_page(request: Request) -> HTMLResponse:
    digest = request.path_params["digest"]
    session_id = request.path_params["session_id"]
    try:
        session = data_tasks.load_session(digest, session_id)
    except data_tasks.DashboardError as e:
        raise HTTPException(400, detail=str(e)) from e
    return HTMLResponse(render_messages_page(session, backend=data_tasks.active_backend()))


async def users_page(request: Request) -> HTMLResponse:
    digest = request.path_params["digest"]
    try:
        users = data_tasks.list_users(digest)
    except data_tasks.DashboardError as e:
        raise HTTPException(400, detail=str(e)) from e
    return HTMLResponse(
        render_users_page(digest, users, backend=data_tasks.active_backend())
    )


async def user_activity_page(request: Request) -> HTMLResponse:
    digest = request.path_params["digest"]
    peer_id = request.path_params["peer_id"]
    try:
        activity = data_tasks.load_user_activity(digest, peer_id)
    except data_tasks.DashboardError as e:
        raise HTTPException(400, detail=str(e)) from e
    return HTMLResponse(
        render_user_activity_page(digest, activity, backend=data_tasks.active_backend())
    )


async def api_status(_: Request) -> JSONResponse:
    return JSONResponse(_backend_banner())


async def api_projects(_: Request) -> JSONResponse:
    try:
        return JSONResponse({"projects": data_tasks.list_projects(), **_backend_banner()})
    except data_tasks.DashboardError as e:
        return _json_error(e)


async def api_sessions(request: Request) -> JSONResponse:
    digest = request.path_params["digest"]
    try:
        return JSONResponse(
            {"digest": digest, "sessions": data_tasks.list_sessions(digest), **_backend_banner()}
        )
    except data_tasks.DashboardError as e:
        return _json_error(e)


async def api_session(request: Request) -> JSONResponse:
    digest = request.path_params["digest"]
    session_id = request.path_params["session_id"]
    try:
        return JSONResponse({**data_tasks.load_session(digest, session_id), **_backend_banner()})
    except data_tasks.DashboardError as e:
        return _json_error(e)


async def api_users(request: Request) -> JSONResponse:
    digest = request.path_params["digest"]
    try:
        return JSONResponse(
            {"digest": digest, "users": data_tasks.list_users(digest), **_backend_banner()}
        )
    except data_tasks.DashboardError as e:
        return _json_error(e)


async def api_user_activity(request: Request) -> JSONResponse:
    digest = request.path_params["digest"]
    peer_id = request.path_params["peer_id"]
    try:
        return JSONResponse(
            {**data_tasks.load_user_activity(digest, peer_id), **_backend_banner()}
        )
    except data_tasks.DashboardError as e:
        return _json_error(e)


def create_app() -> Starlette:
    """Build the dashboard's Starlette app."""
    return Starlette(
        debug=False,
        routes=[
            Route("/", index, name="index"),
            Route("/projects/{digest}", project_page, name="project"),
            Route("/projects/{digest}/sessions/{session_id}", session_page, name="session"),
            Route("/projects/{digest}/users", users_page, name="users"),
            Route(
                "/projects/{digest}/users/{peer_id}",
                user_activity_page,
                name="user_activity",
            ),
            Route("/api/status", api_status, name="api_status"),
            Route("/api/projects", api_projects, name="api_projects"),
            Route("/api/projects/{digest}/sessions", api_sessions, name="api_sessions"),
            Route(
                "/api/projects/{digest}/sessions/{session_id}",
                api_session,
                name="api_session",
            ),
            Route("/api/projects/{digest}/users", api_users, name="api_users"),
            Route(
                "/api/projects/{digest}/users/{peer_id}",
                api_user_activity,
                name="api_user_activity",
            ),
        ],
    )
