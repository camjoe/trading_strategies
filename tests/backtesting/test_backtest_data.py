from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st

from trading.backtesting import backtest_data


def _business_days(periods: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=periods, freq="B")


class TestLoadTickersFromFile:
    def test_load_tickers_from_file_parses_and_deduplicates(self, tmp_path: Path) -> None:
        p = tmp_path / "tickers.txt"
        p.write_text("# comment\nAAPL, msft\n\nAAPL\nNVDA", encoding="utf-8")

        out = backtest_data.load_tickers_from_file(str(p))

        assert out == ["AAPL", "MSFT", "NVDA"]

    def test_load_tickers_from_file_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Ticker file not found"):
            backtest_data.load_tickers_from_file(str(tmp_path / "missing.txt"))


class TestResolveBacktestDates:
    def test_resolve_backtest_dates_conflict_raises(self) -> None:
        with pytest.raises(ValueError, match="Use either --start or --lookback-months"):
            backtest_data.resolve_backtest_dates("2026-01-01", None, 1)

    def test_resolve_backtest_dates_default_window(self) -> None:
        start, end = backtest_data.resolve_backtest_dates(None, "2026-03-14", None)
        assert start == date(2026, 2, 11)
        assert end == date(2026, 3, 14)

    def test_resolve_backtest_dates_invalid_range_raises(self) -> None:
        with pytest.raises(ValueError, match="start date must be before end date"):
            backtest_data.resolve_backtest_dates("2026-03-14", "2026-03-14", None)

    def test_resolve_backtest_dates_rejects_invalid_start_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid start date"):
            backtest_data.resolve_backtest_dates("2026/03/14", None, None)

    def test_resolve_backtest_dates_rejects_non_positive_lookback(self) -> None:
        with pytest.raises(ValueError, match="lookback_months must be > 0"):
            backtest_data.resolve_backtest_dates(None, "2026-03-14", 0)

    def test_resolve_backtest_dates_uses_as_of_when_end_missing(self) -> None:
        start, end = backtest_data.resolve_backtest_dates(None, None, None, as_of=date(2026, 3, 20))

        assert start == date(2026, 2, 17)
        assert end == date(2026, 3, 20)

    @settings(max_examples=30, deadline=None)
    @given(
        as_of=st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)),
        lookback_months=st.integers(min_value=1, max_value=24),
    )
    def test_resolve_backtest_dates_lookback_property(self, as_of: date, lookback_months: int) -> None:
        start, end = backtest_data.resolve_backtest_dates(
            start=None,
            end=None,
            lookback_months=lookback_months,
            as_of=as_of,
        )

        assert end == as_of
        assert start < end
        assert (end - start).days == int(lookback_months * 30.5)


class TestBuildMonthlyUniverse:
    def test_build_monthly_universe_without_history_dir(self) -> None:
        month_to_tickers, all_tickers, warnings = backtest_data.build_monthly_universe(
            default_tickers=["AAPL", "MSFT"],
            start_date=date(2026, 1, 15),
            end_date=date(2026, 3, 15),
            universe_history_dir=None,
        )

        assert set(month_to_tickers.keys()) == {"2026-01", "2026-02", "2026-03"}
        assert all_tickers == ["AAPL", "MSFT"]
        assert warnings == []

    def test_build_monthly_universe_with_missing_month_file_warns(self, tmp_path: Path) -> None:
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

    def test_build_monthly_universe_rejects_empty_default_universe(self) -> None:
        with pytest.raises(ValueError, match="Default ticker universe is empty"):
            backtest_data.build_monthly_universe(
                default_tickers=[],
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                universe_history_dir=None,
            )

    def test_build_monthly_universe_rejects_invalid_history_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist"

        with pytest.raises(ValueError, match="Universe history directory not found"):
            backtest_data.build_monthly_universe(
                default_tickers=["AAPL"],
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                universe_history_dir=str(missing),
            )

    def test_build_monthly_universe_empty_snapshot_falls_back_with_warning(self, tmp_path: Path) -> None:
        hist_dir = tmp_path / "universe"
        hist_dir.mkdir(parents=True)
        (hist_dir / "2026-01.txt").write_text("", encoding="utf-8")

        month_to_tickers, all_tickers, warnings = backtest_data.build_monthly_universe(
            default_tickers=["MSFT"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            universe_history_dir=str(hist_dir),
        )

        assert month_to_tickers["2026-01"] == ["MSFT"]
        assert all_tickers == ["MSFT"]
        assert any("is empty; falling back to default universe" in warning for warning in warnings)


class TestMarketDataFetch:
    def test_fetch_close_history_validates_empty_tickers(self) -> None:
        with pytest.raises(ValueError, match="At least one ticker is required"):
            backtest_data.fetch_close_history([], date(2026, 1, 1), date(2026, 2, 1))

    def test_fetch_close_history_missing_close_column_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_fetch_benchmark_close_empty_series_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nan = float("nan")
        monkeypatch.setattr(
            backtest_data,
            "fetch_close_history",
            lambda _tickers, _start, _end: pd.DataFrame({"SPY": [nan, nan]}),
        )

        with pytest.raises(ValueError, match="No benchmark history for SPY"):
            backtest_data.fetch_benchmark_close("SPY", date(2026, 1, 1), date(2026, 1, 31))

    def test_fetch_benchmark_close_returns_clean_series(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            backtest_data,
            "fetch_close_history",
            lambda _tickers, _start, _end: pd.DataFrame({"SPY": [100.0, float("nan"), 101.0]}),
        )

        out = backtest_data.fetch_benchmark_close("SPY", date(2026, 1, 1), date(2026, 1, 31))

        assert list(out.values) == [100.0, 101.0]
