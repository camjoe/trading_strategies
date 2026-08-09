from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backtesting.services import backtest_data_service as backtest_data
from trading.models.market_data import BAR_CLOSE


def test_build_monthly_universe_without_history_dir() -> None:
    month_to_tickers, all_tickers, warnings = backtest_data._build_monthly_universe(
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

    month_to_tickers, all_tickers, warnings = backtest_data._build_monthly_universe(
        default_tickers=["MSFT"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
        universe_history_dir=str(hist_dir),
    )

    assert month_to_tickers["2026-01"] == ["AAPL"]
    assert month_to_tickers["2026-02"] == ["MSFT"]
    assert all_tickers == ["AAPL", "MSFT"]
    assert any("Universe snapshot missing for 2026-02" in warning for warning in warnings)


def test_build_monthly_universe_rejects_empty_default_universe() -> None:
    with pytest.raises(ValueError, match="Default ticker universe is empty"):
        backtest_data._build_monthly_universe(
            default_tickers=[],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            universe_history_dir=None,
        )


def test_build_monthly_universe_rejects_invalid_history_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    with pytest.raises(ValueError, match="Universe history directory not found"):
        backtest_data._build_monthly_universe(
            default_tickers=["AAPL"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            universe_history_dir=str(missing),
        )


def test_build_monthly_universe_empty_snapshot_falls_back_with_warning(tmp_path: Path) -> None:
    hist_dir = tmp_path / "universe"
    hist_dir.mkdir(parents=True)
    (hist_dir / "2026-01.txt").write_text("", encoding="utf-8")

    month_to_tickers, all_tickers, warnings = backtest_data._build_monthly_universe(
        default_tickers=["MSFT"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        universe_history_dir=str(hist_dir),
    )

    assert month_to_tickers["2026-01"] == ["MSFT"]
    assert all_tickers == ["MSFT"]
    assert any("is empty; falling back to default universe" in warning for warning in warnings)


def test_fetch_benchmark_close_empty_series_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    nan = float("nan")
    monkeypatch.setattr(
        backtest_data,
        "fetch_bar_history",
        lambda _tickers, _start, _end, **_kwargs: {"SPY": pd.DataFrame({BAR_CLOSE: [nan, nan]})},
    )

    with pytest.raises(ValueError, match="No benchmark history for SPY"):
        backtest_data.fetch_benchmark_close("SPY", date(2026, 1, 1), date(2026, 1, 31))


def test_fetch_benchmark_close_returns_clean_series(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backtest_data,
        "fetch_bar_history",
        lambda _tickers, _start, _end, **_kwargs: {"SPY": pd.DataFrame({BAR_CLOSE: [100.0, float("nan"), 101.0]})},
    )

    out = backtest_data.fetch_benchmark_close("SPY", date(2026, 1, 1), date(2026, 1, 31))

    assert list(out.values) == [100.0, 101.0]
