"""Lightweight observability primitives for the Universal Context Router."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class RouterMetrics:
    """In-process counters and latency samples for router operations."""

    route_count: int = 0
    execution_count: int = 0
    blocked_count: int = 0
    confirmation_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    latency_ms: list[float] = field(default_factory=list)

    def observe_latency(self, started_at: float) -> None:
        """Record elapsed time from a perf_counter start."""
        self.latency_ms.append((perf_counter() - started_at) * 1000.0)
        if len(self.latency_ms) > 500:
            self.latency_ms = self.latency_ms[-500:]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable metrics."""
        samples = self.latency_ms
        avg = sum(samples) / len(samples) if samples else 0.0
        return {
            "route_count": self.route_count,
            "execution_count": self.execution_count,
            "blocked_count": self.blocked_count,
            "confirmation_count": self.confirmation_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "latency_avg_ms": avg,
            "latency_samples": len(samples),
        }


_METRICS = RouterMetrics()


def get_router_metrics() -> RouterMetrics:
    """Return process-local router metrics."""
    return _METRICS


def benchmark_summary(iterations: int, elapsed_ms: float) -> dict[str, Any]:
    """Return a small benchmark result payload."""
    return {
        "iterations": iterations,
        "elapsed_ms": elapsed_ms,
        "avg_ms": elapsed_ms / max(iterations, 1),
    }
