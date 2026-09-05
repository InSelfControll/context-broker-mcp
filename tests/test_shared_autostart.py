"""Cold connections share one process, recover stale state, and keep tokens private."""

import asyncio
import json
import os
import subprocess
import sys

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports.stdio import StdioTransport


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_concurrent_cold_connect_and_stale_recovery(tmp_path):
    runtime = tmp_path / "runtime"
    env = dict(os.environ, CONTEXT_BROKER_SHARED_RUNTIME_DIR=str(runtime),
               CONTEXT_BROKER_AUTO_LOAD_ENV="0")

    async def connect_once():
        transport = StdioTransport(command=sys.executable,
            args=["-m", "context_broker", "connect", "--project-root", str(tmp_path)],
            env=env, keep_alive=False)
        async with Client(transport, timeout=90) as client:
            return (await client.call_tool("get_memory_usage", {})).data["pid"]

    async def stop():
        result = await asyncio.to_thread(subprocess.run,
            [sys.executable, "-m", "context_broker", "stop"], env=env,
            capture_output=True, timeout=45)
        assert result.returncode == 0, result.stderr

    try:
        first, second = await asyncio.gather(connect_once(), connect_once())
        assert first == second
        descriptor = runtime / "service.json"
        data = json.loads(descriptor.read_text())
        assert data["pid"] == first
        assert descriptor.stat().st_mode & 0o077 == 0
        async with httpx.AsyncClient(trust_env=False) as client:
            url = f"http://127.0.0.1:{data['port']}"
            assert (await client.get(url + "/health")).status_code == 401
            assert (await client.post(url + "/shutdown")).status_code == 401
        # Both agent pipes are closed; the shared service still answers a new one.
        assert await connect_once() == first
        await stop()
        assert not descriptor.exists()
        descriptor.write_text(json.dumps(data))
        descriptor.chmod(0o600)
        assert await connect_once() != first
    finally:
        await stop()


def test_invalid_project_does_not_start_service(tmp_path):
    runtime = tmp_path / "runtime"
    result = subprocess.run([sys.executable, "-m", "context_broker", "connect",
                             "--project-root", str(tmp_path / "missing")],
        env=dict(os.environ, CONTEXT_BROKER_SHARED_RUNTIME_DIR=str(runtime),
                 CONTEXT_BROKER_AUTO_LOAD_ENV="0"), capture_output=True, timeout=15)
    assert result.returncode != 0
    assert not (runtime / "service.json").exists()
