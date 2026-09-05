"""Exercise actual HTTP sharing and project-bound agent proxies."""

import asyncio
import os
import socket
import subprocess
import sys

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports.stdio import StdioTransport
from fastmcp.client.transports.http import StreamableHttpTransport

from context_broker.shared_ttc.tasks.proxy_tasks import create_agent_proxy


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_shared_service_two_proxies_keep_projects_separate(tmp_path):
    """A shared process survives one client's exit, rejects auth and wrong roots."""
    runtime = tmp_path / "runtime"
    roots = [tmp_path / "a" / "same", tmp_path / "b" / "same"]
    for n, root in enumerate(roots):
        root.mkdir(parents=True)
        (root / "main.py").write_text(f'project_marker = "private_{n}"\n')
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(
        os.environ, CONTEXT_BROKER_SHARED_RUNTIME_DIR=str(runtime), CONTEXT_BROKER_AUTO_LOAD_ENV="0"
    )
    log = (tmp_path / "server.log").open("w+")
    proc = subprocess.Popen(
        [sys.executable, "-m", "context_broker", "serve", "--port", str(port)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
    try:
        async with httpx.AsyncClient(trust_env=False) as http:
            for _ in range(100):
                if proc.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                try:
                    response = await http.post(f"http://127.0.0.1:{port}/mcp", json={})
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
            else:
                pytest.fail("shared service did not start")
            assert response.status_code == 401
        import json

        data = json.loads((runtime / "service.json").read_text())
        service = {"url": f"http://127.0.0.1:{port}/mcp", "token": data["token"]}
        async with Client(create_agent_proxy(str(roots[1]), service)) as second:
            transport = StdioTransport(
                command=sys.executable,
                args=["-m", "context_broker", "connect", "--project-root", str(roots[0])],
                env=env,
                keep_alive=False,
            )
            async with Client(transport) as first:

                async def find(client):
                    return str(
                        (
                            await client.call_tool(
                                "find_in_codebase", {"pattern": "project_marker"}
                            )
                        ).content
                    )

                a, b = await asyncio.gather(find(first), find(second))
                for client in (first, second):
                    usage = await client.call_tool("get_memory_usage", {})
                    assert usage.data["pid"] == proc.pid
                    assert usage.data["model_loaded"] is False
                assert "private_0" in a and "private_1" not in a
                assert "private_1" in b and "private_0" not in b
                with pytest.raises(Exception, match="does not match"):
                    await first.call_tool(
                        "find_in_codebase",
                        {"pattern": "project_marker", "project_root": str(roots[1])},
                    )
            assert proc.poll() is None
            assert "private_1" in await find(second)
        # Missing project identity must not fall back to the service's CWD.
        from mcp.shared.exceptions import McpError

        with pytest.raises(McpError, match="Invalid request"):
            async with Client(
                StreamableHttpTransport(
                    service["url"],
                    auth=service["token"],
                    httpx_client_factory=lambda **kwargs: httpx.AsyncClient(
                        trust_env=False, **kwargs
                    ),
                )
            ):
                pytest.fail("a rootless connection must be rejected at initialization")
        duplicate = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "context_broker", "serve", "--port", str(port)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert duplicate.returncode != 0
        assert json.loads((runtime / "service.json").read_text()) == data

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log.close()


def test_scoped_storage_separates_same_named_projects(tmp_path, monkeypatch):
    from context_broker.shared_ttc.tools.scope import PROJECT_ROOT
    from context_broker.storage_ttc.tools import path_tools

    monkeypatch.setattr(path_tools, "STORAGE_BASE_DIR", str(tmp_path / "global"))
    paths = []
    for parent in ["a", "b"]:
        root = tmp_path / parent / "same"
        root.mkdir(parents=True)
        token = PROJECT_ROOT.set(str(root.resolve()))
        try:
            _, global_path = path_tools.get_storage_dirs("same")
            paths.append(global_path)
            with pytest.raises(ValueError, match="does not match"):
                path_tools.get_storage_dirs("other")
        finally:
            PROJECT_ROOT.reset(token)
    assert paths[0] != paths[1]


def test_proxy_import_does_not_load_ml():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from context_broker.shared_ttc.tasks.proxy_tasks import create_agent_proxy; "
            'create_agent_proxy(".", {"url": "http://127.0.0.1:8771/mcp", "token": "x"*40}); '
            'assert "torch" not in sys.modules; assert "sentence_transformers" not in sys.modules',
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
