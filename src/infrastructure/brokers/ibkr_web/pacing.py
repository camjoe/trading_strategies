"""Process-local pacing guard for IBKR Client Portal API limits."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

# IBKR's documented global Client Portal pacing limit is 10 requests per second.
_GLOBAL_REQUEST_LIMIT = 10

# The global pacing window is one second.
_GLOBAL_REQUEST_WINDOW_SECONDS = 1.0

# Endpoint-specific minimum spacing from the IBKR Client Portal pacing table.
_ENDPOINT_MIN_INTERVAL_SECONDS: dict[tuple[str, str], float] = {
    ("GET", "/portfolio/accounts"): 5.0,
    ("GET", "/portfolio/subaccounts"): 5.0,
    ("GET", "/iserver/account/orders"): 5.0,
    ("GET", "/iserver/account/pnl/partitioned"): 5.0,
    ("GET", "/iserver/account/trades"): 5.0,
    ("GET", "/sso/validate"): 60.0,
    ("GET", "/tickle"): 1.0,
}


class IbWebApiPacingLimiter:
    """Process-local pacing guard for IBKR Client Portal API limits."""

    def __init__(
        self,
        *,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._time_fn = time_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._lock = threading.Lock()
        self._recent_request_times: deque[float] = deque()
        self._endpoint_last_request_times: dict[tuple[str, str], float] = {}

    def wait_for_slot(self, method: str, path: str) -> None:
        endpoint_key = (method.strip().upper(), path)
        while True:
            wait_seconds = 0.0
            with self._lock:
                now = float(self._time_fn())
                self._evict_global_window(now)

                if len(self._recent_request_times) >= _GLOBAL_REQUEST_LIMIT:
                    oldest = self._recent_request_times[0]
                    wait_seconds = max(
                        wait_seconds,
                        oldest + _GLOBAL_REQUEST_WINDOW_SECONDS - now,
                    )

                min_interval = _ENDPOINT_MIN_INTERVAL_SECONDS.get(endpoint_key)
                if min_interval is not None:
                    last_request_at = self._endpoint_last_request_times.get(endpoint_key)
                    if last_request_at is not None:
                        wait_seconds = max(wait_seconds, last_request_at + min_interval - now)

                if wait_seconds <= 0:
                    self._recent_request_times.append(now)
                    if min_interval is not None:
                        self._endpoint_last_request_times[endpoint_key] = now
                    return

            self._sleep_fn(wait_seconds)

    def _evict_global_window(self, now: float) -> None:
        cutoff = now - _GLOBAL_REQUEST_WINDOW_SECONDS
        while self._recent_request_times and self._recent_request_times[0] <= cutoff:
            self._recent_request_times.popleft()


# Shared process-wide default so all clients without an injected limiter pace together.
_DEFAULT_IB_WEB_API_PACING_LIMITER = IbWebApiPacingLimiter()
