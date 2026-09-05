"""Update supported installations without silently leaving a stale shared service."""

import json
import re
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from filelock import FileLock

from context_broker.shared_ttc.tools.runtime_tools import runtime_directory
from context_broker.shared_ttc.tasks.startup_tasks import running_service, stop_service

REPOSITORY = "https://github.com/InSelfControll/context-broker-mcp.git"


def update_commands() -> tuple[list[list[str]], Path | None]:
    """Select the installation owner; never mutate Nix or an arbitrary Python environment."""
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Install uv before updating Context Broker")
    tool_root = subprocess.run([uv, "tool", "dir"], check=True, capture_output=True,
                               text=True, timeout=15).stdout.strip()
    if Path(sys.prefix).resolve() == (Path(tool_root) / "context-broker").resolve():
        # Resolve the trusted upstream branch once; installation uses an immutable SHA.
        ref = subprocess.run(["git", "ls-remote", REPOSITORY, "refs/heads/master"],
                             check=True, capture_output=True, text=True, timeout=60).stdout
        sha = ref.split()[0] if ref.split() else ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError("Could not resolve the Context Broker upstream revision")
        source = f"context-broker[dashboard,integrations] @ git+{REPOSITORY}@{sha}"
        return [[uv, "tool", "install", "--force", "--python", "3.13", source]], None
    metadata = json.loads(distribution("context-broker").read_text("direct_url.json") or "{}")
    root = Path(__file__).resolve().parents[3]
    if metadata.get("dir_info", {}).get("editable") and (root / ".git").exists():
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                               cwd=root, check=True, capture_output=True, text=True,
                               timeout=15).stdout
        if dirty:
            raise RuntimeError("Commit or stash local Context Broker changes before updating")
        return [["git", "pull", "--ff-only"], [uv, "sync", "--all-extras", "--frozen"]], root
    raise RuntimeError("This installation is externally managed; update with its package manager")


def update_runtime(*, check_only: bool = False) -> None:
    """Update dependencies and restart a previously running broker with fresh modules."""
    commands, cwd = update_commands()
    if check_only:
        from rich.console import Console
        Console().print({"commands": commands, "directory": str(cwd) if cwd else None})
        return
    directory = runtime_directory()
    with FileLock(str(directory / "startup.lock"), timeout=65):
        service = running_service()
        if service:
            stop_service(service)
        else:
            # Refuse upgrades under a legacy server without the control endpoint.
            with FileLock(str(directory / "server.lock"), timeout=0):
                pass
        for command in commands:
            subprocess.run(command, cwd=cwd, check=True, timeout=1800)
    if service:
        # A fresh interpreter avoids importing old modules after an in-place update.
        subprocess.run([sys.executable, "-m", "context_broker", "start"], check=True,
                       timeout=90)
