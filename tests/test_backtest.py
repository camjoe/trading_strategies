from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from trading.accounts import create_account
from trading.backtest import BacktestConfig, backtest_report, run_backtest


def _fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        # Uptrend then mild pullback to force both buy and sell decisions.
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def test_run_backtest_persists_isolated_results(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_bt", "trend_v1", 10000.0, "SPY")

    monkeypatch.setattr("trading.backtest.load_tickers_from_file", lambda _path: ["AAPL", "MSFT"])
    monkeypatch.setattr("trading.backtest.fetch_close_history", lambda _tickers, _start, _end: _fake_close_history(_tickers))
    monkeypatch.setattr(
        "trading.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 103.0], index=pd.date_range("2026-01-01", periods=2, freq="B")),
    )

    result = run_backtest(
        conn,
        BacktestConfig(
            account_name="acct_bt",
            tickers_file="trading/trade_universe.txt",
            universe_history_dir=None,
            start="2026-01-01",
            end="2026-03-01",
            lookback_months=None,
            slippage_bps=5.0,
            fee_per_trade=0.0,
            run_name="smoke",
            allow_approximate_leaps=False,
        ),
    )

    assert result.run_id > 0
    assert result.trade_count > 0

    row = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE id = ?", (result.run_id,)).fetchone()
    assert row is not None and int(row["n"]) == 1

    snapshots = conn.execute(
        "SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (result.run_id,)
    ).fetchone()
    assert snapshots is not None and int(snapshots["n"]) >= 2

    paper_trades = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()
    assert paper_trades is not None and int(paper_trades["n"]) == 0


def test_run_backtest_leaps_requires_explicit_approximation_opt_in(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(
        conn,
        "acct_leaps_bt",
        "trend_v1",
        5000.0,
        "SPY",
        instrument_mode="leaps",
        option_strike_offset_pct=5.0,
        option_min_dte=120,
        option_max_dte=365,
        option_type="call",
    )

    monkeypatch.setattr("trading.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr("trading.backtest.fetch_close_history", lambda _tickers, _start, _end: _fake_close_history(_tickers))
    monkeypatch.setattr(
        "trading.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 102.0], index=pd.date_range("2026-01-01", periods=2, freq="B")),
    )

    with pytest.raises(ValueError, match="LEAPs mode backtesting is approximate only"):
        run_backtest(
            conn,
            BacktestConfig(
                account_name="acct_leaps_bt",
                tickers_file="trading/trade_universe.txt",
                universe_history_dir=None,
                start="2026-01-01",
                end="2026-03-01",
                lookback_months=None,
                slippage_bps=5.0,
                fee_per_trade=0.0,
                run_name=None,
                allow_approximate_leaps=False,
            ),
        )

    result = run_backtest(
        conn,
        BacktestConfig(
            account_name="acct_leaps_bt",
            tickers_file="trading/trade_universe.txt",
            universe_history_dir=None,
            start="2026-01-01",
            end="2026-03-01",
            lookback_months=None,
            slippage_bps=5.0,
            fee_per_trade=0.0,
            run_name="approx-ok",
            allow_approximate_leaps=True,
        ),
    )
    assert any("LEAPs mode is approximated" in warning for warning in result.warnings)


def test_backtest_report_returns_summary(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_bt", "trend_v1", 10000.0, "SPY")

    monkeypatch.setattr("trading.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr("trading.backtest.fetch_close_history", lambda _tickers, _start, _end: _fake_close_history(_tickers))
    monkeypatch.setattr(
        "trading.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 105.0], index=pd.date_range("2026-01-01", periods=2, freq="B")),
    )

    result = run_backtest(
        conn,
        BacktestConfig(
            account_name="acct_report_bt",
            tickers_file="trading/trade_universe.txt",
            universe_history_dir=None,
            start="2026-01-01",
            end="2026-03-01",
            lookback_months=None,
            slippage_bps=1.0,
            fee_per_trade=0.0,
            run_name="for-report",
            allow_approximate_leaps=False,
        ),
    )

    summary = backtest_report(conn, result.run_id)
    assert summary["run_id"] == result.run_id
    assert summary["account_name"] == "acct_report_bt"
    assert summary["trade_count"] >= 0
    assert isinstance(summary["total_return_pct"], float)


def test_run_backtest_uses_strategy_signal_resolver(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_sig", "macd_trend", 10000.0, "SPY")

    call_count = {"n": 0}

    def fake_signal(_strategy_name: str, _history: pd.Series) -> str:
        call_count["n"] += 1
        return "hold"

    monkeypatch.setattr("trading.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr("trading.backtest.fetch_close_history", lambda _tickers, _start, _end: _fake_close_history(_tickers))
    monkeypatch.setattr(
        "trading.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 101.0], index=pd.date_range("2026-01-01", periods=2, freq="B")),
    )
    monkeypatch.setattr("trading.backtest.resolve_signal", fake_signal)

    run_backtest(
        conn,
        BacktestConfig(
            account_name="acct_sig",
            tickers_file="trading/trade_universe.txt",
            universe_history_dir=None,
            start="2026-01-01",
            end="2026-03-01",
            lookback_months=None,
            slippage_bps=5.0,
            fee_per_trade=0.0,
            run_name="sig-resolver",
            allow_approximate_leaps=False,
        ),
    )

    assert call_count["n"] > 0


def test_run_backtest_monthly_universe_reconstitution_adds_warning(
    conn,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_account(conn, "acct_universe", "trend_v1", 10000.0, "SPY")

    history_dir = tmp_path / "universe_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "2026-01.txt").write_text("AAPL\n", encoding="utf-8")

    monkeypatch.setattr("trading.backtest.load_tickers_from_file", lambda _path: ["AAPL", "MSFT"])
    monkeypatch.setattr("trading.backtest.fetch_close_history", lambda _tickers, _start, _end: _fake_close_history(_tickers))
    monkeypatch.setattr(
        "trading.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 101.0], index=pd.date_range("2026-01-01", periods=2, freq="B")),
    )

    result = run_backtest(
        conn,
        BacktestConfig(
            account_name="acct_universe",
            tickers_file="trading/trade_universe.txt",
            universe_history_dir=str(history_dir),
            start="2026-01-01",
            end="2026-03-01",
            lookback_months=None,
            slippage_bps=5.0,
            fee_per_trade=0.0,
            run_name="universe-reconstitution",
            allow_approximate_leaps=False,
        ),
    )

    assert any("Monthly universe reconstitution enabled" in warning for warning in result.warnings)
    assert any("Universe snapshot missing" in warning for warning in result.warnings)
