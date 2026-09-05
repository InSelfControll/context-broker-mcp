"""Generate native client config fragments without editing user settings."""

import json
import os
import sys
from pathlib import Path

HOSTS = ("codex", "hermes", "relayhelm", "cursor", "claude-code")
DESTINATIONS = {
    "codex": ".codex/config.toml",
    "hermes": "~/.hermes/config.yaml",
    "relayhelm": "~/.relayhelm/config.yaml",
    "cursor": ".cursor/mcp.json",
    "claude-code": ".mcp.json",
}


def client_config(
    host: str, project_root: str, *, python_executable: str = "", runtime_dir: str = ""
) -> str:
    """Return a TOML or JSON/YAML-compatible fragment for one supported host."""
    if host not in HOSTS:
        raise ValueError(f"Choose one of: {', '.join(HOSTS)}")
    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    # Do not resolve the interpreter symlink: that would lose virtualenv identity.
    executable = python_executable or os.path.abspath(sys.executable)
    if not os.path.isabs(executable):
        raise ValueError("python_executable must be an absolute path")
    env = {"CONTEXT_BROKER_AUTO_LOAD_ENV": "0"}
    if runtime_dir:
        env["CONTEXT_BROKER_SHARED_RUNTIME_DIR"] = str(Path(runtime_dir).expanduser().resolve())
    entry = {
        "command": executable,
        "args": ["-m", "context_broker", "connect", "--project-root", str(root)],
        "env": env,
    }
    if host == "codex":
        return (
            "[mcp_servers.context-broker]\n"
            f"command = {json.dumps(executable)}\n"
            f'args = {json.dumps(entry["args"])}\n'
            "startup_timeout_sec = 30\ntool_timeout_sec = 600\n"
            "[mcp_servers.context-broker.env]\n"
            + "".join(f"{key} = {json.dumps(value)}\n" for key, value in env.items())
        )
    if host in {"hermes", "relayhelm"}:
        entry.update(timeout=600, connect_timeout=30, elicitation={"enabled": True, "timeout": 300})
        return json.dumps({"mcp_servers": {"context-broker": entry}}, indent=2) + "\n"
    if host == "claude-code":
        entry.update(type="stdio", timeout=600000)
    return json.dumps({"mcpServers": {"context-broker": entry}}, indent=2) + "\n"
