"""Start or reuse one authenticated broker without attaching it to an agent's pipes."""

import os
import subprocess
import sys
import time

import httpx
from filelock import FileLock, Timeout

from context_broker.shared_ttc.tools.runtime_tools import read_service, runtime_directory

STARTUP_TIMEOUT = 60


def running_service() -> dict[str, str] | None:
    """Recognize a ready broker using its private bearer token, never just an open port."""
    try:
        service = read_service()
    except FileNotFoundError:
        return None
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            response = client.get(
                service["url"].removesuffix("/mcp") + "/health",
                headers={"Authorization": f"Bearer {service['token']}"},
            )
        if response.status_code == 200 and response.json() == {"service": "context-broker"}:
            return service
    except (httpx.HTTPError, ValueError):
        return None
    return None


def ensure_service() -> dict[str, str]:
    """Serialize cold starts and wait for readiness; leave a healthy service untouched."""
    directory = runtime_directory()
    with FileLock(str(directory / "startup.lock"), timeout=STARTUP_TIMEOUT + 5):
        service = running_service()
        if service:
            return service
        # A live older or still-starting broker owns this lock. Never overwrite
        # its descriptor or guess process identity from a possibly recycled PID.
        owner = FileLock(str(directory / "server.lock"), timeout=0)
        try:
            with owner:
                pass
        except Timeout:
            raise RuntimeError("Broker is already starting or needs a manual restart after upgrade")
        env = dict(os.environ, CONTEXT_BROKER_SHARED_RUNTIME_DIR=str(directory),
                   CONTEXT_BROKER_AUTO_LOAD_ENV="0")
        # Discard service output: shared storage can contain user data, and a
        # detached child must never retain any agent stdio handles.
        child = subprocess.Popen(
            [sys.executable, "-m", "context_broker", "serve", "--port", "0"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT
        try:
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError("Broker startup failed; run context-broker serve for diagnostics")
                service = running_service()
                if service:
                    return service
                time.sleep(0.1)
            raise TimeoutError("Broker did not become ready within 60 seconds")
        except BaseException:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            raise


def stop_service(service: dict[str, str]) -> None:
    """Ask the authenticated process to stop and wait for its ownership lock to release."""
    with httpx.Client(trust_env=False, timeout=5) as client:
        response = client.post(
            service["url"].removesuffix("/mcp") + "/shutdown",
            headers={"Authorization": f"Bearer {service['token']}"},
        )
        response.raise_for_status()
    with FileLock(str(runtime_directory() / "server.lock"), timeout=30):
        pass
