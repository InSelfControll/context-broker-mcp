"""One bounded LRU pool shared by project-scoped cache namespaces."""

from collections import OrderedDict
from collections.abc import Iterator, MutableMapping
import sys
from threading import RLock
from typing import Any


def retained_bytes(value: Any, seen: set[int] | None = None) -> int:
    """Estimate retained cache payload size, counting ndarray buffers once."""
    seen = seen if seen is not None else set()
    if id(value) in seen:
        return 0
    seen.add(id(value))
    if hasattr(value, "nbytes"):
        return int(value.nbytes) + 128
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size + sum(
            retained_bytes(k, seen) + retained_bytes(v, seen)
            for k, v in value.items()
            if k not in {"model", "encoder"}
        )
    if isinstance(value, (list, tuple)):
        return size + sum(retained_bytes(item, seen) for item in value)
    return size


class MemoryPool:
    """Budget retained cache payloads, independently of model and in-flight memory."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._entries: OrderedDict[tuple[str, str], tuple[Any, int]] = OrderedDict()
        self._lock = RLock()
        self.used_bytes = 0
        self.evictions = 0

    def namespace(self, name: str) -> "PoolNamespace":
        """Return a mapping view without creating a separate cache allocation."""
        return PoolNamespace(self, name)

    def snapshot(self) -> dict[str, int]:
        """Return aggregate counts without exposing project identifiers or data."""
        with self._lock:
            return {
                "budget_bytes": self.max_bytes,
                "retained_bytes": self.used_bytes,
                "entries": len(self._entries),
                "evictions": self.evictions,
            }


class PoolNamespace(MutableMapping[str, Any]):
    """A project-keyed mapping backed by a process-wide memory pool."""

    def __init__(self, pool: MemoryPool, name: str) -> None:
        self.pool, self.name = pool, name

    def __getitem__(self, key: str) -> Any:
        with self.pool._lock:
            entry = (self.name, key)
            value, _ = self.pool._entries[entry]
            self.pool._entries.move_to_end(entry)
            return value

    def __setitem__(self, key: str, value: Any) -> None:
        weight = retained_bytes(value) + retained_bytes(key)
        with self.pool._lock:
            entry = (self.name, key)
            old = self.pool._entries.pop(entry, None)
            if old is not None:
                self.pool.used_bytes -= old[1]
            if weight > self.pool.max_bytes:
                return
            while self.pool._entries and self.pool.used_bytes + weight > self.pool.max_bytes:
                _, (_, removed) = self.pool._entries.popitem(last=False)
                self.pool.used_bytes -= removed
                self.pool.evictions += 1
            self.pool._entries[entry] = (value, weight)
            self.pool.used_bytes += weight

    def __delitem__(self, key: str) -> None:
        with self.pool._lock:
            _, weight = self.pool._entries.pop((self.name, key))
            self.pool.used_bytes -= weight

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove in one critical section so concurrent eviction cannot race."""
        with self.pool._lock:
            entry = self.pool._entries.pop((self.name, key), None)
            if entry is None:
                return default
            value, weight = entry
            self.pool.used_bytes -= weight
            return value

    def __iter__(self) -> Iterator[str]:
        with self.pool._lock:
            return iter([key for namespace, key in self.pool._entries if namespace == self.name])

    def __len__(self) -> int:
        with self.pool._lock:
            return sum(namespace == self.name for namespace, _ in self.pool._entries)

    def clear(self) -> None:
        """Clear only this namespace, atomically with respect to eviction."""
        with self.pool._lock:
            for key in list(self):
                del self[key]
