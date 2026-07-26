"""In-memory metrics for credential-preserving gateway handoffs."""

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class GatewayMetrics:
    """Track the aggregate size of prepared external handoffs."""

    prepared_requests: int = 0
    candidate_tokens: int = 0
    sent_tokens: int = 0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def saved_tokens(self) -> int:
        """Return the total number of context tokens removed from handoffs."""
        return max(0, self.candidate_tokens - self.sent_tokens)

    def record_handoff(self, candidate_tokens: int, sent_tokens: int) -> None:
        """Atomically add one successfully prepared handoff to the aggregate metrics."""
        with self._lock:
            self.prepared_requests += 1
            self.candidate_tokens += candidate_tokens
            self.sent_tokens += sent_tokens

    def snapshot(self) -> dict[str, int]:
        """Return an atomic snapshot of the aggregate handoff metrics."""
        with self._lock:
            return {
                "prepared_requests": self.prepared_requests,
                "candidate_tokens": self.candidate_tokens,
                "sent_tokens": self.sent_tokens,
                "saved_tokens": self.saved_tokens,
            }


METRICS = GatewayMetrics()
