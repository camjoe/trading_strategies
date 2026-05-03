from __future__ import annotations

import pandas as pd
import pytest

from paper_trading_ui.backend.services.accounts import benchmark as account_benchmark


def test_build_live_benchmark_overlay_aligns_snapshot_period(monkeypatch) -> None:
    close_index = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"])
    close_series = pd.Series([100.0, 105.0, 110.0], index=close_index)
    monkeypatch.setattr(
        account_benchmark,
        "fetch_benchmark_close_history",
        lambda _ticker, *, start_date, end_date: close_series,
    )

    overlay = account_benchmark.build_live_benchmark_overlay(
        {"benchmark": "SPY", "equity": 1200.0},
        [
            {"snapshot_time": "2026-01-04T00:00:00Z", "equity": 1200.0},
            {"snapshot_time": "2026-01-02T00:00:00Z", "equity": 1000.0},
            {"snapshot_time": "2026-01-03T00:00:00Z", "equity": 1100.0},
        ],
    )

    assert overlay is not None
    assert overlay["benchmark"] == "SPY"
    assert overlay["startTime"] == "2026-01-02T00:00:00Z"
    assert overlay["endTime"] == "2026-01-04T00:00:00Z"
    assert overlay["benchmarkReturnPct"] == pytest.approx(10.0)
    assert overlay["alphaPct"] == pytest.approx(10.0)
    points = overlay["points"]
    assert len(points) == 3
    assert points[-1]["benchmarkEquity"] == pytest.approx(1100.0)


def test_attach_live_benchmark_summary_sets_fields() -> None:
    summary = {"name": "acct"}
    overlay = {
        "benchmarkReturnPct": 6.0,
        "alphaPct": 2.5,
        "benchmarkEquity": 1060.0,
        "startTime": "2026-01-01T00:00:00Z",
        "endTime": "2026-01-10T00:00:00Z",
    }

    account_benchmark.attach_live_benchmark_summary(summary, overlay)

    assert summary["liveBenchmarkReturnPct"] == pytest.approx(6.0)
    assert summary["liveAlphaPct"] == pytest.approx(2.5)
    assert summary["liveBenchmarkEquity"] == pytest.approx(1060.0)
    assert summary["liveBenchmarkStartTime"] == "2026-01-01T00:00:00Z"
    assert summary["liveBenchmarkEndTime"] == "2026-01-10T00:00:00Z"
