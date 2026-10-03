"""Deterministic outbound-call guard: pace calls and cap the total per process.

A small, provider-agnostic guard for code that makes external API/network calls.
Two independent, deterministic protections — both opt-in (a ``0`` / ``None`` limit
disables that protection):

* ``min_interval_seconds`` — enforce a minimum spacing between calls by blocking
  (sleeping) until the interval has elapsed, so a tight loop cannot burst-hammer a
  provider into rate-limiting us.
* ``max_total_calls`` — a hard ceiling on cumulative calls for this limiter's
  lifetime; the call past the ceiling raises :class:`RateLimitExceeded` instead of
  proceeding, so an accidental unbounded loop is stopped deterministically rather
  than fanning out real traffic.

Call :meth:`RateLimiter.acquire` immediately before each external call — and after
any cache lookup, so served-from-cache work neither paces nor counts. The clock and
sleep functions are injectable for deterministic tests, and the guard is
thread-safe (it sleeps outside the lock, mirroring the broker pacing limiter).

This is the shared primitive; a concrete adapter owns its own limits (e.g. the
yfinance provider builds one from env vars). Other outbound adapters — brokers,
external feature providers — can adopt the same primitive rather than re-rolling
call guards.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimitExceeded(RuntimeError):
    """Raised when a :class:`RateLimiter`'s cumulative call budget is exhausted.

    Signals a likely runaway loop: the guarded code tried to make more external
    calls than the configured ceiling allows. Not caught internally — it should
    surface so the operator can investigate rather than be silently swallowed.
    """


class RateLimiter:
    """Paces outbound calls and caps their cumulative count (see module docstring)."""

    def __init__(
        self,
        *,
        min_interval_seconds: float = 0.0,
        max_total_calls: int | None = None,
        name: str = "",
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")
        if max_total_calls is not None and max_total_calls < 0:
            raise ValueError("max_total_calls must be >= 0 or None")
        self._min_interval = float(min_interval_seconds)
        self._max_total_calls = max_total_calls
        self._name = name or "rate_limiter"
        self._time_fn = time_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._lock = threading.Lock()
        self._call_count = 0
        self._last_call_at: float | None = None

    def acquire(self) -> None:
        """Reserve one call slot, blocking for pacing; raise if the budget is spent.

        Raises :class:`RateLimitExceeded` when the cumulative-call ceiling is reached
        (checked before any wait, so an exhausted budget fails fast). Otherwise blocks
        until ``min_interval_seconds`` has elapsed since the previous call, then records
        this call and returns.
        """
        while True:
            with self._lock:
                if self._max_total_calls is not None and self._call_count >= self._max_total_calls:
                    raise RateLimitExceeded(
                        f"{self._name}: cumulative call budget exhausted "
                        f"(max_total_calls={self._max_total_calls}); refusing further calls."
                    )
                now = float(self._time_fn())
                wait_seconds = 0.0
                if self._min_interval > 0.0 and self._last_call_at is not None:
                    wait_seconds = self._last_call_at + self._min_interval - now
                if wait_seconds <= 0.0:
                    self._last_call_at = now
                    self._call_count += 1
                    return
            # Sleep outside the lock so a waiting caller does not block reads/reset.
            self._sleep_fn(wait_seconds)

    @property
    def call_count(self) -> int:
        """Cumulative calls recorded since construction or the last :meth:`reset`."""
        with self._lock:
            return self._call_count

    def reset(self) -> None:
        """Clear the call count and pacing state (e.g. between independent runs/tests)."""
        with self._lock:
            self._call_count = 0
            self._last_call_at = None
