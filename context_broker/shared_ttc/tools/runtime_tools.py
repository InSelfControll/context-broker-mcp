"""Private same-user service discovery; no tokens in CLI arguments or logs."""

import json
import os
from pathlib import Path

from context_broker.config import SHARED_RUNTIME_DIR


def runtime_directory() -> Path:
    """Create a private directory, rejecting unsafe existing permissions."""
    path = Path(SHARED_RUNTIME_DIR).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("shared runtime directory must be owned by you with permissions 0700")
    return path


def read_service() -> dict[str, str]:
    """Read the local service descriptor without accepting remote token destinations."""
    path = runtime_directory() / "service.json"
    info = path.stat()
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("shared service descriptor must have permissions 0600")
    data = json.loads(path.read_text())
    port = data.get("port")
    token = data.get("token")
    if not isinstance(port, int) or not 0 < port < 65536:
        raise ValueError("invalid shared service port")
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("invalid shared service token")
    return {"url": f"http://127.0.0.1:{port}/mcp", "token": token}
