from __future__ import annotations

from datetime import date

import pandas as pd
import pandas.testing as pdt
import pytest

from trading.models.portfolio import EquitySnapshotRecord
from trading.services.analysis import benchmark


def _snapshot(snapshot_time: str, equity: float) -> EquitySnapshotRecord:
    """Build a snapshot record carrying only the fields the overlay reads."""
    return EquitySnapshotRecord(
        id=0,
        account_id=0,
        book_id=None,
        snapshot_time=snapshot_time,
        cash=0.0,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


class StubProvider:
    def __init__(self, result: pd.DataFrame | None) -> None:
        self.result = result
        self.calls: list[tuple[list[str], date, date]] = []

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame | None:
        self.calls.append((tickers, start_date, end_date))
        return self.result


def test_fetch_benchmark_close_history_returns_none_for_blank_ticker() -> None:
    provider = StubProvider(pd.DataFrame({"SPY": [100.0]}))

    result = benchmark.fetch_benchmark_close_history(
        "   ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        provider=provider,
    )

    assert result is None
    assert provider.calls == []


def test_fetch_benchmark_close_history_returns_none_when_provider_returns_none() -> None:
    provider = StubProvider(None)

    result = benchmark.fetch_benchmark_close_history(
        "spy",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        provider=provider,
    )

    assert result is None
    assert provider.calls == [(["SPY"], date(2024, 1, 2), date(2024, 1, 3))]


def test_fetch_benchmark_close_history_returns_none_when_ticker_column_is_missing() -> None:
    provider = StubProvider(pd.DataFrame({"QQQ": [100.0, 101.0]}))

    result = benchmark.fetch_benchmark_close_history(
        "spy",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        provider=provider,
    )

    assert result is None


def test_fetch_benchmark_close_history_returns_dropna_series_for_matching_ticker() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    provider = StubProvider(pd.DataFrame({"SPY": [100.0, None, 103.5]}, index=index))

    result = benchmark.fetch_benchmark_close_history(
        "spy",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
        provider=provider,
    )

    expected = pd.Series([100.0, 103.5], index=index[[0, 2]], name="SPY")
    pdt.assert_series_equal(result, expected)


def test_fetch_benchmark_close_history_uses_first_column_for_multi_level_result() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    columns = pd.MultiIndex.from_tuples(
        [("SPY", "close"), ("SPY", "adjusted_close")],
    )
    provider = StubProvider(
        pd.DataFrame(
            [
                [100.0, 200.0],
                [None, 201.0],
                [103.0, 202.0],
            ],
            index=index,
            columns=columns,
        )
    )

    result = benchmark.fetch_benchmark_close_history(
        "spy",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
        provider=provider,
    )

    expected = pd.Series([100.0, 103.0], index=index[[0, 2]], name="close")
    pdt.assert_series_equal(result, expected)


def test_build_live_benchmark_overlay_returns_none_when_too_few_snapshots() -> None:
    result = benchmark.build_live_benchmark_overlay(
        "SPY",
        [_snapshot("2024-01-02T16:00:00Z", 100.0)],
    )

    assert result is None


def test_build_live_benchmark_overlay_returns_none_for_blank_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        benchmark,
        "fetch_benchmark_close_history",
        lambda *_args, **_kwargs: pytest.fail("fetch_benchmark_close_history should not be called"),
    )

    result = benchmark.build_live_benchmark_overlay(
        "  ",
        [
            _snapshot("2024-01-02T16:00:00Z", 100.0),
            _snapshot("2024-01-03T16:00:00Z", 101.0),
        ],
    )

    assert result is None


@pytest.mark.parametrize("starting_equity", [0.0, -1.0])
def test_build_live_benchmark_overlay_returns_none_for_non_positive_starting_equity(
    monkeypatch: pytest.MonkeyPatch,
    starting_equity: float,
) -> None:
    monkeypatch.setattr(
        benchmark,
        "fetch_benchmark_close_history",
        lambda *_args, **_kwargs: pytest.fail("fetch_benchmark_close_history should not be called"),
    )

    result = benchmark.build_live_benchmark_overlay(
        "SPY",
        [
            _snapshot("2024-01-02T16:00:00Z", starting_equity),
            _snapshot("2024-01-03T16:00:00Z", 101.0),
        ],
    )

    assert result is None


def test_build_live_benchmark_overlay_returns_none_when_fetch_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_fetch(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(benchmark, "fetch_benchmark_close_history", raise_fetch)

    result = benchmark.build_live_benchmark_overlay(
        "SPY",
        [
            _snapshot("2024-01-02T16:00:00Z", 100.0),
            _snapshot("2024-01-03T16:00:00Z", 105.0),
        ],
    )

    assert result is None


@pytest.mark.parametrize(
    "close_history",
    [
        None,
        pd.Series(dtype=float),
    ],
)
def test_build_live_benchmark_overlay_returns_none_for_missing_or_empty_close_history(
    monkeypatch: pytest.MonkeyPatch,
    close_history: pd.Series | None,
) -> None:
    monkeypatch.setattr(benchmark, "fetch_benchmark_close_history", lambda *_args, **_kwargs: close_history)

    result = benchmark.build_live_benchmark_overlay(
        "SPY",
        [
            _snapshot("2024-01-02T16:00:00Z", 100.0),
            _snapshot("2024-01-03T16:00:00Z", 105.0),
        ],
    )

    assert result is None


def test_build_live_benchmark_overlay_returns_none_when_fewer_than_two_points_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_history = pd.Series(
        [100.0, 101.0],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    prices = iter([100.0, 100.0, None])

    monkeypatch.setattr(benchmark, "fetch_benchmark_close_history", lambda *_args, **_kwargs: close_history)
    monkeypatch.setattr(benchmark, "_close_price_on_or_before", lambda *_args, **_kwargs: next(prices))

    result = benchmark.build_live_benchmark_overlay(
        "SPY",
        [
            _snapshot("2024-01-02T16:00:00Z", 100.0),
            _snapshot("2024-01-03T16:00:00Z", 105.0),
        ],
    )

    assert result is None


def test_build_live_benchmark_overlay_computes_sorted_overlay_and_returns_expected_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_history = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(
            [
                "2024-01-02T21:00:00Z",
                "2024-01-03T21:00:00Z",
                "2024-01-04T21:00:00Z",
            ],
            utc=True,
        ),
        name="SPY",
    )
    snapshots = [
        _snapshot("2024-01-04T16:00:00Z", 150.0),
        _snapshot("2024-01-02T16:00:00Z", 100.0),
        _snapshot("2024-01-03T16:00:00Z", 90.0),
    ]

    monkeypatch.setattr(benchmark, "fetch_benchmark_close_history", lambda *_args, **_kwargs: close_history)

    result = benchmark.build_live_benchmark_overlay(" spy ", snapshots)

    assert result is not None
    assert set(result) == {
        "accountReturnPct",
        "alphaPct",
        "benchmark",
        "benchmarkEquity",
        "benchmarkReturnPct",
        "endingEquity",
        "endTime",
        "points",
        "startingEquity",
        "startTime",
    }
    assert result["benchmark"] == "SPY"
    assert result["startTime"] == "2024-01-02T16:00:00Z"
    assert result["endTime"] == "2024-01-04T16:00:00Z"
    assert result["startingEquity"] == pytest.approx(100.0)
    assert result["endingEquity"] == pytest.approx(150.0)
    assert result["benchmarkEquity"] == pytest.approx(121.0)
    assert result["accountReturnPct"] == pytest.approx(50.0)
    assert result["benchmarkReturnPct"] == pytest.approx(21.0)
    assert result["alphaPct"] == pytest.approx(29.0)
    assert result["points"] == [
        {
            "time": "2024-01-02T16:00:00Z",
            "accountEquity": 100.0,
            "benchmarkEquity": pytest.approx(100.0),
        },
        {
            "time": "2024-01-03T16:00:00Z",
            "accountEquity": 90.0,
            "benchmarkEquity": pytest.approx(110.0),
        },
        {
            "time": "2024-01-04T16:00:00Z",
            "accountEquity": 150.0,
            "benchmarkEquity": pytest.approx(121.0),
        },
    ]


def test_attach_live_benchmark_summary_sets_none_fields_and_returns_same_summary() -> None:
    summary = {"name": "acct"}

    result = benchmark.attach_live_benchmark_summary(summary, None)

    assert result is summary
    assert summary == {
        "name": "acct",
        "liveBenchmarkReturnPct": None,
        "liveAlphaPct": None,
        "liveBenchmarkEquity": None,
        "liveBenchmarkStartTime": None,
        "liveBenchmarkEndTime": None,
    }


def test_attach_live_benchmark_summary_maps_overlay_fields_and_returns_same_summary() -> None:
    summary = {"name": "acct"}
    overlay = {
        "benchmarkReturnPct": 8.5,
        "alphaPct": 1.25,
        "benchmarkEquity": 1085.0,
        "startTime": "2024-01-02T16:00:00Z",
        "endTime": "2024-01-04T16:00:00Z",
    }

    result = benchmark.attach_live_benchmark_summary(summary, overlay)

    assert result is summary
    assert summary == {
        "name": "acct",
        "liveBenchmarkReturnPct": 8.5,
        "liveAlphaPct": 1.25,
        "liveBenchmarkEquity": 1085.0,
        "liveBenchmarkStartTime": "2024-01-02T16:00:00Z",
        "liveBenchmarkEndTime": "2024-01-04T16:00:00Z",
    }
