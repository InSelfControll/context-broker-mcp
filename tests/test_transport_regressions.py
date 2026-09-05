"""Transport shutdown and dashboard responsiveness regression tests."""

import asyncio
import threading
from time import monotonic

import anyio
import httpx

from context_broker.dashboard_ttc.tools import web_app
from context_broker.server_ttc.tools.ws_transport import websocket_server


def test_websocket_context_exit_closes_idle_reader_and_writer() -> None:
    class IdleWebSocket:
        async def receive_text(self):
            await anyio.sleep_forever()

    async def run():
        with anyio.fail_after(1):
            async with websocket_server(IdleWebSocket()):
                pass

    asyncio.run(run())


def test_slow_dashboard_backend_does_not_block_health_requests(monkeypatch) -> None:
    release = threading.Event()

    def slow_projects():
        release.wait(timeout=1)
        return []

    monkeypatch.setattr(web_app.data_tasks, "list_projects", slow_projects)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web_app.create_app()), base_url="http://test"
        ) as client:
            started = monotonic()
            slow = asyncio.create_task(client.get("/api/projects"))
            try:
                await asyncio.sleep(0.02)
                response = await client.get("/api/status")
                assert response.status_code == 200
                assert monotonic() - started < 0.75
            finally:
                release.set()
                await slow

    asyncio.run(run())
