from __future__ import annotations

import pandas as pd
import pytest
from paper_trading_web.backend.services.accounts import benchmark as account_benchmark

import trading.services.analysis.benchmark as analysis_benchmark
from tests.support.analysis import snapshot_record


def test_build_live_benchmark_overlay_aligns_snapshot_period(monkeypatch) -> None:
    close_index = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"])
    close_series = pd.Series([100.0, 105.0, 110.0], index=close_index)
    monkeypatch.setattr(
        analysis_benchmark,
        "fetch_benchmark_close_history",
        lambda _ticker, *, start_date, end_date, provider=None: close_series,
    )

    overlay = account_benchmark.build_live_benchmark_overlay(
        "SPY",
        [
            snapshot_record("2026-01-04T00:00:00Z", 1200.0),
            snapshot_record("2026-01-02T00:00:00Z", 1000.0),
            snapshot_record("2026-01-03T00:00:00Z", 1100.0),
        ],
    )

    assert overlay is not None
    assert overlay["benchmark"] == "SPY"
    assert overlay["start_time"] == "2026-01-02T00:00:00Z"
    assert overlay["end_time"] == "2026-01-04T00:00:00Z"
    assert overlay["benchmark_return_pct"] == pytest.approx(10.0)
    assert overlay["alpha_pct"] == pytest.approx(10.0)
    points = overlay["points"]
    assert len(points) == 3
    assert points[-1]["benchmark_equity"] == pytest.approx(1100.0)


def test_attach_live_benchmark_summary_sets_fields() -> None:
    summary = {"name": "acct"}
    # The overlay is the snake_case analysis payload; attach maps it to camelCase.
    overlay = {
        "benchmark_return_pct": 6.0,
        "alpha_pct": 2.5,
        "benchmark_equity": 1060.0,
        "start_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-01-10T00:00:00Z",
    }

    account_benchmark.attach_live_benchmark_summary(summary, overlay)

    assert summary["liveBenchmarkReturnPct"] == pytest.approx(6.0)
    assert summary["liveAlphaPct"] == pytest.approx(2.5)
    assert summary["liveBenchmarkEquity"] == pytest.approx(1060.0)
    assert summary["liveBenchmarkStartTime"] == "2026-01-01T00:00:00Z"
    assert summary["liveBenchmarkEndTime"] == "2026-01-10T00:00:00Z"


def test_attach_live_benchmark_summary_sets_none_when_overlay_missing() -> None:
    summary = {"name": "acct"}

    result = account_benchmark.attach_live_benchmark_summary(summary, None)

    assert result is summary
    assert summary == {
        "name": "acct",
        "liveBenchmarkReturnPct": None,
        "liveAlphaPct": None,
        "liveBenchmarkEquity": None,
        "liveBenchmarkStartTime": None,
        "liveBenchmarkEndTime": None,
    }
