"""In-memory metrics for credential-preserving gateway handoffs."""

from dataclasses import dataclass


@dataclass
class GatewayMetrics:
    """Track the aggregate size of prepared external handoffs."""

    prepared_requests: int = 0
    candidate_tokens: int = 0
    sent_tokens: int = 0

    @property
    def saved_tokens(self) -> int:
        """Return the total number of context tokens removed from handoffs."""
        return max(0, self.candidate_tokens - self.sent_tokens)


METRICS = GatewayMetrics()
