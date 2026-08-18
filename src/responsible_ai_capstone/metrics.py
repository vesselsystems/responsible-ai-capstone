"""Thread-safe in-process metrics for the small capstone service."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class Metrics:
    requests: int = 0
    errors: int = 0
    no_evidence: int = 0
    llm_fallbacks: int = 0
    total_latency_ms: float = 0.0

    def __post_init__(self) -> None:
        self._lock = Lock()

    def record(
        self,
        *,
        latency_ms: float,
        error: bool = False,
        no_evidence: bool = False,
        llm_fallback: bool = False,
    ) -> None:
        with self._lock:
            self.requests += 1
            self.total_latency_ms += latency_ms
            self.errors += int(error)
            self.no_evidence += int(no_evidence)
            self.llm_fallbacks += int(llm_fallback)

    def prometheus(self) -> str:
        with self._lock:
            average = self.total_latency_ms / self.requests if self.requests else 0.0
            return "\n".join(
                [
                    "# HELP capstone_requests_total Total /ask requests.",
                    "# TYPE capstone_requests_total counter",
                    f"capstone_requests_total {self.requests}",
                    "# HELP capstone_errors_total Requests that raised an internal error.",
                    "# TYPE capstone_errors_total counter",
                    f"capstone_errors_total {self.errors}",
                    "# HELP capstone_no_evidence_total Requests with no matching evidence.",
                    "# TYPE capstone_no_evidence_total counter",
                    f"capstone_no_evidence_total {self.no_evidence}",
                    "# HELP capstone_llm_fallbacks_total LLM calls that fell back to "
                    "evidence-only mode.",
                    "# TYPE capstone_llm_fallbacks_total counter",
                    f"capstone_llm_fallbacks_total {self.llm_fallbacks}",
                    "# HELP capstone_request_latency_ms_average Average request latency.",
                    "# TYPE capstone_request_latency_ms_average gauge",
                    f"capstone_request_latency_ms_average {average:.3f}",
                    "",
                ]
            )
