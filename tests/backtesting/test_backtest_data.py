from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from trading.backtesting import backtest_data


def _business_days(periods: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=periods, freq="B")


def test_load_tickers_from_file_parses_and_deduplicates(tmp_path: Path) -> None:
    p = tmp_path / "tickers.txt"
    p.write_text("# comment\nAAPL, msft\n\nAAPL\nNVDA", encoding="utf-8")

    out = backtest_data.load_tickers_from_file(str(p))

    assert out == ["AAPL", "MSFT", "NVDA"]


def test_load_tickers_from_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Ticker file not found"):
        backtest_data.load_tickers_from_file(str(tmp_path / "missing.txt"))


def test_resolve_backtest_dates_conflict_raises() -> None:
    with pytest.raises(ValueError, match="Use either --start or --lookback-months"):
        backtest_data.resolve_backtest_dates("2026-01-01", None, 1)


def test_resolve_backtest_dates_default_window() -> None:
    start, end = backtest_data.resolve_backtest_dates(None, "2026-03-14", None)
    assert start == date(2026, 2, 11)
    assert end == date(2026, 3, 14)


def test_resolve_backtest_dates_invalid_range_raises() -> None:
    with pytest.raises(ValueError, match="start date must be before end date"):
        backtest_data.resolve_backtest_dates("2026-03-14", "2026-03-14", None)


def test_build_monthly_universe_without_history_dir() -> None:
    month_to_tickers, all_tickers, warnings = backtest_data.build_monthly_universe(
        default_tickers=["AAPL", "MSFT"],
        start_date=date(2026, 1, 15),
        end_date=date(2026, 3, 15),
        universe_history_dir=None,
    )

    assert set(month_to_tickers.keys()) == {"2026-01", "2026-02", "2026-03"}
    assert all_tickers == ["AAPL", "MSFT"]
    assert warnings == []


def test_build_monthly_universe_with_missing_month_file_warns(tmp_path: Path) -> None:
    hist_dir = tmp_path / "universe"
    hist_dir.mkdir(parents=True)
    (hist_dir / "2026-01.txt").write_text("AAPL\n", encoding="utf-8")

    month_to_tickers, all_tickers, warnings = backtest_data.build_monthly_universe(
        default_tickers=["MSFT"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
        universe_history_dir=str(hist_dir),
    )

    assert month_to_tickers["2026-01"] == ["AAPL"]
    assert month_to_tickers["2026-02"] == ["MSFT"]
    assert all_tickers == ["AAPL", "MSFT"]
    assert any("Universe snapshot missing for 2026-02" in warning for warning in warnings)


def test_fetch_close_history_validates_empty_tickers() -> None:
    with pytest.raises(ValueError, match="At least one ticker is required"):
        backtest_data.fetch_close_history([], date(2026, 1, 1), date(2026, 2, 1))


def test_fetch_close_history_missing_close_column_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    idx = _business_days(3)
    # MultiIndex frame without Close level for the requested multi-ticker path.
    hist = pd.DataFrame(
        {
            ("Open", "AAPL"): [1.0, 1.0, 1.0],
            ("Open", "MSFT"): [1.0, 1.0, 1.0],
        },
        index=idx,
    )

    monkeypatch.setattr("common.market_data.yf.download", lambda **_kwargs: hist)

    with pytest.raises(ValueError, match="missing Close column"):
        backtest_data.fetch_close_history(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 1, 31))


def test_fetch_benchmark_close_empty_series_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    nan = float("nan")
    monkeypatch.setattr(
        backtest_data,
        "fetch_close_history",
        lambda _tickers, _start, _end: pd.DataFrame({"SPY": [nan, nan]}),
    )

    with pytest.raises(ValueError, match="No benchmark history for SPY"):
        backtest_data.fetch_benchmark_close("SPY", date(2026, 1, 1), date(2026, 1, 31))
