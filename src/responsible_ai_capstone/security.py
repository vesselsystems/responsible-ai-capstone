"""Small dependency-free request controls used by the local HTTP service."""

from __future__ import annotations

import ipaddress
import math
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a request admission check."""

    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


class RateLimiter:
    """A bounded in-process sliding-window limiter keyed by client identifier.

    This is appropriate for a single local process only.  It deliberately does not
    claim to coordinate limits across workers or hosts; a deployment would need a
    shared, trusted limiter for that use case.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_clients: int = 10_000,
    ) -> None:
        if max_clients < 1:
            raise ValueError("max_clients must be positive")
        self._clock = clock
        self._max_clients = max_clients
        self._lock = Lock()
        self._windows: dict[str, deque[float]] = {}
        self._configuration: tuple[int, int] | None = None

    def configure(self, *, requests: int, window_seconds: int) -> None:
        """Apply a validated policy and clear state when the policy changes."""

        if requests < 1 or window_seconds < 1:
            raise ValueError("rate-limit values must be positive")
        configuration = (requests, window_seconds)
        with self._lock:
            if self._configuration != configuration:
                self._windows.clear()
                self._configuration = configuration

    def check(
        self,
        client_id: str,
        *,
        requests: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        self.configure(requests=requests, window_seconds=window_seconds)
        now = self._clock()
        with self._lock:
            if client_id not in self._windows and len(self._windows) >= self._max_clients:
                # Dict insertion order gives a deterministic bounded FIFO eviction.
                self._windows.pop(next(iter(self._windows)))
            timestamps = self._windows.setdefault(client_id, deque())
            cutoff = now - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= requests:
                retry_after = max(1, math.ceil(timestamps[0] + window_seconds - now))
                return RateLimitDecision(False, 0, retry_after)

            timestamps.append(now)
            return RateLimitDecision(True, requests - len(timestamps), 0)

    def allow(self, client_id: str, *, requests: int, window_seconds: int) -> bool:
        """Compatibility convenience for callers that only need a boolean."""

        return self.check(
            client_id,
            requests=requests,
            window_seconds=window_seconds,
        ).allowed

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


def _proxy_networks(values: tuple[str, ...] | list[str]) -> tuple[object, ...]:
    """Parse a trusted-network tuple for callers outside the environment config."""

    networks: list[object] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def trusted_client_id(
    client_host: str | None,
    forwarded_for: str | None = None,
    *,
    trust_proxy_headers: bool = False,
    trusted_proxy_cidrs: tuple[str, ...] | list[str] = (),
) -> str:
    """Return a stable client key without trusting spoofable headers by default.

    ``X-Forwarded-For`` is considered only when forwarding is enabled *and* the
    direct peer belongs to the configured trusted proxy CIDR allowlist.  The first
    syntactically valid address is used, and invalid values fall back to the direct
    peer.  The API middleware hashes the result before logging it.
    """

    direct = (client_host or "unknown").strip() or "unknown"
    if not trust_proxy_headers or not forwarded_for:
        return direct
    try:
        direct_address = ipaddress.ip_address(direct)
    except ValueError:
        return direct
    networks = _proxy_networks(trusted_proxy_cidrs)
    if not any(direct_address in network for network in networks):
        return direct
    for candidate in forwarded_for.split(","):
        candidate = candidate.strip()
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return direct
