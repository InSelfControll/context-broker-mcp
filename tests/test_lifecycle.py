from context_broker import lifecycle
from context_broker.indexer_ttc.tools import state


def test_stdio_disconnect_exits_while_editor_parent_remains_alive() -> None:
    """Closing the host pipe must stop even a broker busy outside its event loop."""
    import os
    import select
    import subprocess
    import sys

    import pytest

    if not sys.platform.startswith("linux"):
        pytest.skip("Linux pipe-hangup watchdog")
    code = (
        "from context_broker.lifecycle import start_lifecycle_watchdogs; "
        "import time; start_lifecycle_watchdogs(); "
        "print('ready', flush=True); time.sleep(60)"
    )
    env = dict(
        os.environ, CONTEXT_BROKER_TRANSPORT="stdio", CONTEXT_BROKER_EXIT_WHEN_PARENT_DIES="0"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert select.select([process.stdout], [], [], 20)[0], "broker did not initialize"
        assert process.stdout.readline() == b"ready\n"
        assert process.poll() is None
        process.stdin.close()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def test_release_expensive_resources_clears_in_memory_state() -> None:
    state.INDEXES["demo"] = {"paths": ["a.py"]}
    state.QUERY_CACHE["demo"] = {"query": "auth"}
    state.LAST_TOKEN_REPORTS["demo"] = {"total_tokens": 10}
    state.LAST_PERSISTED_TOKEN_REPORT_HASHES["demo"] = "hash"
    state.SHARED_MODEL = object()
    state.ENCODER = object()

    assert lifecycle._release_expensive_resources() is True
    assert state.INDEXES == {}
    assert state.QUERY_CACHE == {}
    assert state.LAST_TOKEN_REPORTS == {}
    assert state.LAST_PERSISTED_TOKEN_REPORT_HASHES == {}
    assert state.SHARED_MODEL is None
    assert state.ENCODER is None


def test_startup_ancestors_missing_detects_dead_process() -> None:
    original = lifecycle._pid_exists
    lifecycle._pid_exists = lambda pid: pid != 222
    try:
        assert lifecycle._startup_ancestors_missing((111, 222, 333)) is True
        assert lifecycle._startup_ancestors_missing((111, 333)) is False
    finally:
        lifecycle._pid_exists = original
