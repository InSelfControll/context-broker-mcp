"""
HTML templates for the dashboard.

Rendered inline (no on-disk template files) so the module stays self-contained.
Markup is intentionally minimal — this is a debug viewer, not a product UI.
"""

from datetime import datetime, timezone
from html import escape
from typing import Any


def _fmt_ts(value: Any) -> str:
    try:
        f = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    if f <= 0:
        return "—"
    return datetime.fromtimestamp(f, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


_STYLE = """
<style>
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 2rem;
         background: #0e1116; color: #e6edf3; }
  header { display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1.5rem; }
  h1 { margin: 0; font-size: 1.4rem; }
  .pill { background: #21262d; padding: 0.2rem 0.6rem; border-radius: 999px;
          font-size: 0.8rem; color: #7ee787; }
  .crumb { color: #8b949e; }
  a { color: #79c0ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; font-size: 0.8rem; text-transform: uppercase; }
  tr:hover td { background: #161b22; }
  .empty { color: #8b949e; padding: 1rem 0; }
  .error { background: #3d1c1c; border: 1px solid #6f2424;
           color: #ffa198; padding: 0.75rem 1rem; border-radius: 6px; }
  .msg { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 0.5rem;
         border: 1px solid #21262d; background: #161b22; }
  .msg.user { border-left: 3px solid #79c0ff; }
  .msg.assistant { border-left: 3px solid #7ee787; }
  .msg .peer { font-size: 0.75rem; color: #8b949e; margin-bottom: 0.3rem;
               display: flex; justify-content: space-between; gap: 1rem; }
  .msg .peer .ts { color: #6e7681; font-variant-numeric: tabular-nums; }
  .msg pre { margin: 0; white-space: pre-wrap; word-break: break-word;
             font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
"""


def _layout(title: str, body: str, backend: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>{_STYLE}</head><body>"
        f"<header><h1>Context Broker — Cross-Chat Dashboard</h1>"
        f"<span class='pill'>backend: {escape(backend or 'none')}</span></header>"
        f"{body}</body></html>"
    )


def render_projects_page(
    projects: list[dict[str, Any]], *, backend: str, error: str | None = None
) -> str:
    body = ""
    if error:
        body += f"<div class='error'>{escape(error)}</div>"
    if not projects:
        body += "<p class='empty'>No projects with stored cross-chat context.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td><a href='/projects/{escape(p['digest'])}'>{escape(p['name'] or 'unknown')}</a></td>"
            f"<td>{escape(p.get('root') or '')}</td>"
            f"<td>{int(p.get('session_count', 0))}</td>"
            f"<td><code>{escape(p['digest'])}</code></td>"
            "</tr>"
            for p in projects
        )
        body += (
            "<table><thead><tr><th>Project</th><th>Root</th>"
            "<th>Sessions</th><th>Digest</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    return _layout("Projects", body, backend)


def render_project_page(
    digest: str, sessions: list[dict[str, Any]], *, backend: str
) -> str:
    crumb = (
        f"<p class='crumb'><a href='/'>← all projects</a> &middot; "
        f"digest <code>{escape(digest)}</code> &middot; "
        f"<a href='/projects/{escape(digest)}/users'>users</a></p>"
    )
    if not sessions:
        body = crumb + "<p class='empty'>No sessions recorded for this project.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td><a href='/projects/{escape(digest)}/sessions/{escape(s['session_id'])}'>"
            f"{escape(s['session_id'])}</a></td>"
            f"<td>{escape(s['full_session_id'])}</td>"
            f"<td>{int(s.get('message_count', 0))}</td>"
            f"<td>{escape(_fmt_ts(s.get('last_message_at')))}</td>"
            "</tr>"
            for s in sessions
        )
        body = (
            crumb
            + "<table><thead><tr><th>Session</th><th>Full ID</th>"
            "<th>Messages</th><th>Last message</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    return _layout(f"Project {digest}", body, backend)


def _classify_peer(peer_id: str) -> str:
    name = (peer_id or "").lower()
    if "assistant" in name or "agent" in name:
        return "assistant"
    return "user"


def render_users_page(
    digest: str, users: list[dict[str, Any]], *, backend: str
) -> str:
    crumb = (
        f"<p class='crumb'><a href='/'>all projects</a> &rsaquo; "
        f"<a href='/projects/{escape(digest)}'>{escape(digest)}</a> &rsaquo; users</p>"
    )
    if not users:
        body = crumb + "<p class='empty'>No user activity recorded for this project yet.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td><a href='/projects/{escape(digest)}/users/{escape(u['peer_id'])}'>"
            f"{escape(u['peer_id'])}</a></td>"
            f"<td>{escape(_fmt_ts(u.get('first_seen')))}</td>"
            f"<td>{escape(_fmt_ts(u.get('last_seen')))}</td>"
            f"<td>{int(u.get('request_count', 0))}</td>"
            "</tr>"
            for u in users
        )
        body = (
            crumb
            + "<table><thead><tr><th>User</th><th>First seen</th>"
            "<th>Last seen</th><th>Requests</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    return _layout(f"Users for {digest}", body, backend)


def render_user_activity_page(
    digest: str, activity: dict[str, Any], *, backend: str
) -> str:
    peer_id = activity.get("peer_id", "")
    crumb = (
        f"<p class='crumb'><a href='/'>all projects</a> &rsaquo; "
        f"<a href='/projects/{escape(digest)}'>{escape(digest)}</a> &rsaquo; "
        f"<a href='/projects/{escape(digest)}/users'>users</a> &rsaquo; "
        f"<code>{escape(peer_id)}</code></p>"
    )
    summary = (
        "<table><thead><tr><th>First seen</th><th>Last seen</th>"
        "<th>Requests</th><th>Log length</th></tr></thead><tbody><tr>"
        f"<td>{escape(_fmt_ts(activity.get('first_seen')))}</td>"
        f"<td>{escape(_fmt_ts(activity.get('last_seen')))}</td>"
        f"<td>{int(activity.get('request_count', 0))}</td>"
        f"<td>{int(activity.get('request_log_length', 0))}</td>"
        "</tr></tbody></table>"
    )
    requests = activity.get("requests", [])
    if not requests:
        log_block = "<p class='empty'>No request history.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td>{escape(_fmt_ts(r.get('timestamp')))}</td>"
            f"<td><a href='/projects/{escape(digest)}/sessions/{escape(r.get('session_id', ''))}'>"
            f"{escape(r.get('session_id', ''))}</a></td>"
            "</tr>"
            for r in requests
        )
        log_block = (
            "<h3 style='margin:1.5rem 0 0.5rem;font-weight:500;'>Request log "
            f"<span class='crumb'>({len(requests)} entries)</span></h3>"
            "<table><thead><tr><th>Timestamp</th><th>Session</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    return _layout(f"User {peer_id}", crumb + summary + log_block, backend)


def render_messages_page(session: dict[str, Any], *, backend: str) -> str:
    digest = session.get("project", {}).get("digest", "")
    project_name = session.get("project", {}).get("name", "unknown")
    session_id = session.get("session_id", "")
    crumb = (
        "<p class='crumb'>"
        f"<a href='/'>all projects</a> &rsaquo; "
        f"<a href='/projects/{escape(digest)}'>{escape(project_name)}</a> &rsaquo; "
        f"session <code>{escape(session_id)}</code></p>"
    )
    messages = session.get("messages", [])
    if not messages:
        body = crumb + "<p class='empty'>No messages stored for this session.</p>"
    else:
        rendered = "".join(
            f"<div class='msg {_classify_peer(m.get('peer_id', ''))}'>"
            "<div class='peer'>"
            f"<span>{escape(str(m.get('peer_id', 'unknown')))}</span>"
            f"<span class='ts'>{escape(_fmt_ts(m.get('created_at')))}</span>"
            "</div>"
            f"<pre>{escape(str(m.get('content', '')))}</pre>"
            "</div>"
            for m in messages
        )
        body = crumb + rendered
    return _layout(f"Session {session_id}", body, backend)
