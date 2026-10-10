"""Deterministic tests for the general RateLimiter: pacing spacing, the cumulative
call ceiling, and reset. A fake clock advanced by the injected sleep keeps timing
deterministic (no real waiting)."""

from __future__ import annotations

import pytest

from common.rate_limit import RateLimiter, RateLimitExceeded


class _FakeClock:
    """A monotonic clock whose only advance is the injected sleep — so pacing math
    is exercised without real time passing."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _limiter(clock: _FakeClock, **kwargs) -> RateLimiter:
    return RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep, **kwargs)


class TestPacing:
    def test_first_call_does_not_wait(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=1.0)

        limiter.acquire()

        assert clock.sleeps == []
        assert limiter.call_count == 1

    def test_second_immediate_call_waits_the_interval(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=1.0)

        limiter.acquire()
        limiter.acquire()  # no time elapsed → must sleep the full interval

        assert clock.sleeps == [pytest.approx(1.0)]
        assert clock.now == pytest.approx(1.0)
        assert limiter.call_count == 2

    def test_no_wait_when_interval_already_elapsed(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=1.0)

        limiter.acquire()
        clock.now += 5.0  # plenty of time passes between calls
        limiter.acquire()

        assert clock.sleeps == []

    def test_zero_interval_never_paces(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=0.0)

        for _ in range(5):
            limiter.acquire()

        assert clock.sleeps == []
        assert limiter.call_count == 5


class TestCeiling:
    def test_raises_past_the_budget(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, max_total_calls=3)

        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        with pytest.raises(RateLimitExceeded, match="budget exhausted"):
            limiter.acquire()
        # The rejected call is not counted.
        assert limiter.call_count == 3

    def test_ceiling_checked_before_waiting(self) -> None:
        # An exhausted budget fails fast rather than sleeping first.
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=10.0, max_total_calls=1)

        limiter.acquire()
        with pytest.raises(RateLimitExceeded):
            limiter.acquire()
        assert clock.sleeps == []  # no wait before the refusal

    def test_none_ceiling_is_unlimited(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, max_total_calls=None)

        for _ in range(50):
            limiter.acquire()

        assert limiter.call_count == 50


class TestResetAndValidation:
    def test_reset_clears_count_and_pacing(self) -> None:
        clock = _FakeClock()
        limiter = _limiter(clock, min_interval_seconds=1.0, max_total_calls=1)

        limiter.acquire()
        limiter.reset()
        limiter.acquire()  # allowed again, and no pacing wait after reset

        assert limiter.call_count == 1
        assert clock.sleeps == []

    def test_rejects_negative_config(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(min_interval_seconds=-1.0)
        with pytest.raises(ValueError):
            RateLimiter(max_total_calls=-1)
