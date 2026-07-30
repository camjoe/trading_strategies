from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from tests.support.backtesting import bars_from_closes
from tests.support.strategies import ensure_strategy_id_for_label
from trading.backtesting.backtest import BacktestConfig, run_backtest
from trading.backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_latest_backtest_run_id_for_account_strategy,
    fetch_recent_backtest_runs,
)
from trading.services.accounts import create_account


def _fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def _backtest_config(account_name: str) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="src/infrastructure/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=1.0,
        fee_per_trade=0.0,
        run_name="contract",
        allow_approximate_leaps=False,
    )


def test_report_repository_contract_returns_rows(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_repo", "trend_v1", 10000.0, "SPY")
    monkeypatch.setattr("trading.backtesting.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_bar_history",
        lambda _tickers, _start, _end, **_kwargs: bars_from_closes(_fake_close_history(_tickers)),
    )
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end, **_kwargs: pd.Series(
            [100.0, 102.0],
            index=pd.date_range("2026-01-01", periods=2, freq="B"),
        ),
    )

    result = run_backtest(conn, _backtest_config("acct_report_repo"))

    run_row = fetch_backtest_report_run(conn, result.run_id)
    snapshot_rows = fetch_backtest_report_snapshots(conn, result.run_id)
    trade_rows = fetch_backtest_report_trades(conn, result.run_id)

    assert run_row is not None
    assert len(snapshot_rows) >= 2
    assert isinstance(trade_rows, list)


# ---------------------------------------------------------------------------
# fetch_recent_backtest_runs
# ---------------------------------------------------------------------------


def _insert_account_and_runs(conn: sqlite3.Connection, account_name: str, run_count: int) -> list[int]:
    """Insert a fresh account plus *run_count* backtest_runs; returns list of run ids."""
    create_account(conn, account_name, "trend_v1", 10_000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()["id"])
    run_ids = []
    for i in range(run_count):
        row = conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id, strategy_id, run_name, start_date, end_date,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                ensure_strategy_id_for_label(conn, "trend_v1"),
                f"run_{i}",
                "2026-01-01",
                "2026-01-31",
                0.0,
                0.0,
                "src/infrastructure/config/trade_universe.txt",
                "",
                "",
                f"2026-02-0{i + 1}T00:00:00Z",
            ),
        )
        run_ids.append(int(row.lastrowid))
    conn.commit()
    return run_ids


def test_fetch_recent_backtest_runs_respects_limit(conn: sqlite3.Connection) -> None:
    _insert_account_and_runs(conn, "acct_recent", 3)

    rows = fetch_recent_backtest_runs(conn, limit=2)

    assert len(rows) == 2
    # Results are ordered newest-first (DESC by id).
    assert rows[0]["run_name"] == "run_2"
    assert rows[1]["run_name"] == "run_1"


# ---------------------------------------------------------------------------
# fetch_latest_backtest_run_for_account
# ---------------------------------------------------------------------------


def test_fetch_latest_backtest_run_for_account_returns_latest_row(conn: sqlite3.Connection) -> None:
    _insert_account_and_runs(conn, "acct_latest_row", 2)

    row = fetch_latest_backtest_run_for_account(conn, account_name="acct_latest_row")

    assert row is not None
    assert row["run_name"] == "run_1"
    assert row["account_name"] == "acct_latest_row"


def test_fetch_latest_backtest_run_for_account_returns_none_when_no_runs(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_empty_runs", "trend_v1", 1_000.0, "SPY")
    conn.commit()

    row = fetch_latest_backtest_run_for_account(conn, account_name="acct_empty_runs")

    assert row is None


# ---------------------------------------------------------------------------
# fetch_latest_backtest_run_id_for_account
# ---------------------------------------------------------------------------


def test_fetch_latest_backtest_run_id_for_account_returns_int(conn: sqlite3.Connection) -> None:
    run_ids = _insert_account_and_runs(conn, "acct_run_id", 2)

    result = fetch_latest_backtest_run_id_for_account(conn, account_name="acct_run_id")

    assert result == run_ids[-1]


def test_fetch_latest_backtest_run_id_for_account_returns_none_when_no_runs(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_no_runs_id", "trend_v1", 1_000.0, "SPY")
    conn.commit()

    result = fetch_latest_backtest_run_id_for_account(conn, account_name="acct_no_runs_id")

    assert result is None


# ---------------------------------------------------------------------------
# fetch_latest_backtest_run_id_for_account_strategy
# ---------------------------------------------------------------------------


def test_fetch_latest_backtest_run_id_for_account_strategy_returns_id(conn: sqlite3.Connection) -> None:
    run_ids = _insert_account_and_runs(conn, "acct_strat_id", 2)
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_strat_id",)).fetchone()["id"])

    result = fetch_latest_backtest_run_id_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name="trend_v1",
    )

    assert result == run_ids[-1]


def test_fetch_latest_backtest_run_id_for_account_strategy_returns_none_for_no_match(
    conn: sqlite3.Connection,
) -> None:
    _insert_account_and_runs(conn, "acct_strat_nomatch", 1)
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_strat_nomatch",)).fetchone()["id"])

    result = fetch_latest_backtest_run_id_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name="nonexistent_strategy_v99",
    )

    assert result is None
