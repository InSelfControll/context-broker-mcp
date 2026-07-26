"""Opt-in production-path verification for AnyIO worker-thread offloading."""

from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Any

import pytest

from context_broker.gateway_ttc.tasks import downstream_tasks
from context_broker.gateway_ttc.tasks.downstream_tasks import GatewayDownstreamRuntime
from context_broker.router_ttc.tools.registry_tools import ToolDescriptor, ToolRegistry


@pytest.mark.anyio
@pytest.mark.skipif(
    os.environ.get("CONTEXT_BROKER_TEST_REAL_THREADS") != "1",
    reason="set CONTEXT_BROKER_TEST_REAL_THREADS=1 outside restricted sandboxes",
)
async def test_runtime_uses_real_anyio_worker_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real runtime path and prove synchronous stages leave the event loop."""
    main_thread = threading.get_ident()
    worker_threads: list[int] = []

    def record(function: Any) -> Any:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            worker_threads.append(threading.get_ident())
            return function(*args, **kwargs)

        return wrapped

    monkeypatch.setattr(
        downstream_tasks,
        "prepare_gateway_components",
        record(downstream_tasks.prepare_gateway_components),
    )
    monkeypatch.setattr(
        downstream_tasks,
        "build_external_handoff",
        record(downstream_tasks.build_external_handoff),
    )
    monkeypatch.setattr(
        downstream_tasks,
        "preflight_gateway_plan",
        record(downstream_tasks.preflight_gateway_plan),
    )
    monkeypatch.setattr(
        downstream_tasks,
        "execute_gateway_plan_api",
        record(downstream_tasks.execute_gateway_plan_api),
    )

    registry = ToolRegistry(cache_dir=tmp_path / "registry")
    registry.register(
        ToolDescriptor(
            id="inspect",
            name="inspect",
            description="inspect source",
            risk_level="low",
        )
    )
    runtime = GatewayDownstreamRuntime(registry=registry)

    handoff = await runtime.prepare_gateway_request("inspect", token_budget=1200)
    result = await runtime.execute_gateway_plan(
        handoff["route"]["plan"],
        handoff["issuance"]["claim"],
    )

    assert result["status"] == "ok"
    assert len(worker_threads) == 4
    assert all(thread_id != main_thread for thread_id in worker_threads)
    await runtime.close()
