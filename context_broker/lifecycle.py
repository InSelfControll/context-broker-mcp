"""
Process and resource lifecycle helpers for the MCP server.
"""

from __future__ import annotations

import ctypes
import gc
import os
import signal
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from context_broker.config import (
    EXIT_WHEN_PARENT_DIES,
    IDLE_RESOURCE_CLEANUP_INTERVAL_SECONDS,
    IDLE_RESOURCE_TIMEOUT_SECONDS,
    PARENT_POLL_INTERVAL_SECONDS,
)
from context_broker.indexer_ttc.tools import state
from context_broker.utils import log

_PR_SET_PDEATHSIG = 1
_WATCHDOG_LOCK = threading.Lock()
_LAST_ACTIVITY_AT = time.monotonic()
_ACTIVE_OPERATIONS = 0
_WATCHDOGS_STARTED = False


def start_lifecycle_watchdogs() -> None:
    """Start background lifecycle watchdogs once per process."""
    global _WATCHDOGS_STARTED

    with _WATCHDOG_LOCK:
        if _WATCHDOGS_STARTED:
            return
        _WATCHDOGS_STARTED = True
        _mark_activity_locked()
        startup_chain = _get_startup_ancestor_chain()

    if EXIT_WHEN_PARENT_DIES and startup_chain:
        _arm_parent_death_signal(startup_chain[0])
        threading.Thread(
            target=_monitor_parent_chain,
            args=(startup_chain,),
            name="context-broker-parent-watchdog",
            daemon=True,
        ).start()

    if IDLE_RESOURCE_TIMEOUT_SECONDS > 0:
        threading.Thread(
            target=_monitor_idle_resources,
            name="context-broker-idle-cleanup",
            daemon=True,
        ).start()


def mark_activity() -> None:
    """Record broker activity without changing active-operation count."""
    with _WATCHDOG_LOCK:
        _mark_activity_locked()


def begin_operation() -> None:
    """Record the start of a broker operation."""
    global _ACTIVE_OPERATIONS

    with _WATCHDOG_LOCK:
        _ACTIVE_OPERATIONS += 1
        _mark_activity_locked()


def end_operation() -> None:
    """Record the end of a broker operation."""
    global _ACTIVE_OPERATIONS

    with _WATCHDOG_LOCK:
        _ACTIVE_OPERATIONS = max(0, _ACTIVE_OPERATIONS - 1)
        _mark_activity_locked()


@contextmanager
def tracked_activity() -> Iterator[None]:
    """Track an active broker operation."""
    begin_operation()
    try:
        yield
    finally:
        end_operation()


def _mark_activity_locked() -> None:
    global _LAST_ACTIVITY_AT
    _LAST_ACTIVITY_AT = time.monotonic()


def _get_startup_ancestor_chain() -> tuple[int, ...]:
    """Capture the initial parent chain for orphan detection."""
    chain: list[int] = []
    pid = os.getppid()
    seen: set[int] = set()

    while pid > 1 and pid not in seen:
        chain.append(pid)
        seen.add(pid)
        next_pid = _read_parent_pid(pid)
        if next_pid is None:
            break
        pid = next_pid

    return tuple(chain)


def _read_parent_pid(pid: int) -> int | None:
    """Read a process parent PID from /proc when available."""
    stat_path = f"/proc/{pid}/stat"
    try:
        with open(stat_path, encoding="utf-8") as handle:
            stat_line = handle.read().strip()
    except OSError:
        return None

    if ") " not in stat_line:
        return None

    _, tail = stat_line.rsplit(") ", 1)
    parts = tail.split()
    if len(parts) < 2:
        return None

    try:
        return int(parts[1])
    except ValueError:
        return None


def _arm_parent_death_signal(expected_parent_pid: int) -> None:
    """Ask the kernel to terminate us if our immediate parent dies."""
    if not sys.platform.startswith("linux"):
        return

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
        if result != 0:
            errno_value = ctypes.get_errno()
            log(
                f"⚠️ Failed to arm parent-death signal (errno={errno_value}); "
                "falling back to polling watchdog",
                "WARN",
            )
            return
    except Exception as exc:
        log(f"⚠️ Failed to arm parent-death signal: {exc}", "WARN")
        return

    if os.getppid() != expected_parent_pid:
        _exit_orphaned_process("Host process exited during startup")


def _monitor_parent_chain(startup_chain: tuple[int, ...]) -> None:
    """Exit if the startup parent chain disappears and leaves us orphaned."""
    while True:
        time.sleep(PARENT_POLL_INTERVAL_SECONDS)

        if os.getppid() != startup_chain[0]:
            _exit_orphaned_process("Immediate parent changed")

        if _startup_ancestors_missing(startup_chain):
            _exit_orphaned_process("Host/editor process tree disappeared")


def _startup_ancestors_missing(startup_chain: tuple[int, ...]) -> bool:
    """Return true when any startup ancestor has exited."""
    return any(not _pid_exists(pid) for pid in startup_chain if pid > 1)


def _pid_exists(pid: int) -> bool:
    """Check process existence with a Linux fast-path and portable fallback."""
    if pid <= 0:
        return False

    if sys.platform.startswith("linux"):
        return os.path.exists(f"/proc/{pid}")

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _monitor_idle_resources() -> None:
    """Release heavy in-memory resources after prolonged inactivity."""
    while True:
        time.sleep(IDLE_RESOURCE_CLEANUP_INTERVAL_SECONDS)

        with _WATCHDOG_LOCK:
            idle_for_seconds = time.monotonic() - _LAST_ACTIVITY_AT
            if _ACTIVE_OPERATIONS > 0 or idle_for_seconds < IDLE_RESOURCE_TIMEOUT_SECONDS:
                continue

            released = _release_expensive_resources()

        if released:
            gc.collect()
            log(
                f"🧹 Released idle model and index caches after "
                f"{int(idle_for_seconds)}s of inactivity"
            )


def _release_expensive_resources() -> bool:
    """Clear in-memory caches and models when the broker is idle."""
    had_resources = any(
        (
            bool(state.INDEXES),
            bool(state.QUERY_CACHE),
            bool(state.LAST_TOKEN_REPORTS),
            bool(state.LAST_PERSISTED_TOKEN_REPORT_HASHES),
            state.SHARED_MODEL is not None,
            state.ENCODER is not None,
        )
    )
    if not had_resources:
        return False

    state.INDEXES.clear()
    state.QUERY_CACHE.clear()
    state.LAST_TOKEN_REPORTS.clear()
    state.LAST_PERSISTED_TOKEN_REPORT_HASHES.clear()
    state.SHARED_MODEL = None
    state.ENCODER = None
    return True


def _exit_orphaned_process(reason: str) -> None:
    """Terminate the broker when its host has disappeared."""
    log(f"🛑 {reason}; shutting down orphaned Context Broker process", "WARN")
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(1)
    os._exit(0)
