from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import pytest

from backtesting.backtest import run_backtest
from backtesting.models import BacktestConfig
from backtesting.repositories.runs import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_leaderboard_rows,
    fetch_recent_backtest_runs,
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_backtest_trade,
)
from tests.support.backtesting import bars_from_closes
from tests.support.strategies import ensure_strategy_id_for_label
from trading.services.accounts import create_account


def _backtest_config(
    account_name: str,
    *,
    run_name: str,
    end: str = "2026-01-31",
    slippage_bps: float = 5.0,
) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="src/infrastructure/config/trade_universes/default.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end=end,
        lookback_months=None,
        slippage_bps=slippage_bps,
        fee_per_trade=0.0,
        run_name=run_name,
        allow_approximate_leaps=False,
    )


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
                "src/infrastructure/config/trade_universes/default.txt",
                "",
                "",
                f"2026-02-0{i + 1}T00:00:00Z",
            ),
        )
        run_ids.append(int(row.lastrowid))
    conn.commit()
    return run_ids


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------


def test_inserts_run_trade_and_snapshot(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_repo", "trend_v1", 10000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_repo",)).fetchone()["id"])

    run_id = insert_backtest_run(
        conn,
        account_id=account_id,
        strategy_name="trend_v1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        cfg=_backtest_config("acct_repo", run_name="repo-test"),
        warnings=["w1", "w2"],
        benchmark_ticker="SPY",
        benchmark_return_pct=1.5,
    )

    insert_backtest_trade(
        conn,
        run_id=run_id,
        trade_time="2026-01-02",
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        fee=0.0,
        slippage_bps=5.0,
        note="note",
    )
    insert_backtest_snapshot(
        conn,
        run_id=run_id,
        snapshot_time="2026-01-02",
        cash=9900.0,
        market_value=100.0,
        equity=10000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    conn.commit()

    run_row = conn.execute(
        "SELECT run_name, warnings, benchmark_ticker, benchmark_return_pct FROM backtest_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    trades = conn.execute("SELECT COUNT(*) AS n FROM backtest_executions WHERE run_id = ?", (run_id,)).fetchone()
    snaps = conn.execute("SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (run_id,)).fetchone()

    assert run_row is not None
    assert run_row["run_name"] == "repo-test"
    assert "w1 | w2" == run_row["warnings"]
    assert int(trades["n"]) == 1
    assert int(snaps["n"]) == 1
    # Frozen on the row so readers never recompute it.
    assert run_row["benchmark_ticker"] == "SPY"
    assert run_row["benchmark_return_pct"] == 1.5


# ---------------------------------------------------------------------------
# report reads
# ---------------------------------------------------------------------------


def _fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def test_report_reads_return_rows(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_repo", "trend_v1", 10000.0, "SPY")
    monkeypatch.setattr("backtesting.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr(
        "backtesting.backtest.fetch_bar_history",
        lambda _tickers, _start, _end, **_kwargs: bars_from_closes(_fake_close_history(_tickers)),
    )
    monkeypatch.setattr(
        "backtesting.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end, **_kwargs: pd.Series(
            [100.0, 102.0],
            index=pd.date_range("2026-01-01", periods=2, freq="B"),
        ),
    )

    cfg = _backtest_config("acct_report_repo", run_name="contract", end="2026-03-01", slippage_bps=1.0)
    result = run_backtest(conn, cfg)

    run_row = fetch_backtest_report_run(conn, result.run_id)
    snapshot_rows = fetch_backtest_report_snapshots(conn, result.run_id)
    trade_rows = fetch_backtest_report_trades(conn, result.run_id)

    assert run_row is not None
    assert len(snapshot_rows) >= 2
    assert isinstance(trade_rows, list)


def test_fetch_recent_backtest_runs_respects_limit(conn: sqlite3.Connection) -> None:
    _insert_account_and_runs(conn, "acct_recent", 3)

    rows = fetch_recent_backtest_runs(conn, limit=2)

    assert len(rows) == 2
    # Results are ordered newest-first (DESC by id).
    assert rows[0]["run_name"] == "run_2"
    assert rows[1]["run_name"] == "run_1"


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
# leaderboard reads
# ---------------------------------------------------------------------------


def test_leaderboard_fetches_rows_and_equity_curve(conn, bt_repo_account, seed_bt_run) -> None:
    account_name, account_id = bt_repo_account

    run_id = seed_bt_run(
        account_id,
        strategy_name="trend",
        run_name="lb-run",
        created_at="2026-02-01T00:00:00Z",
    )
    conn.execute(
        """
        INSERT INTO backtest_executions (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-15", "AAPL", "buy", 1.0, 100.0, 0.0, 0.0, "test"),
    )
    conn.commit()

    rows = fetch_leaderboard_rows(
        conn,
        limit=10,
        account_name=account_name,
        strategy="trend",
    )

    assert len(rows) == 1
    assert int(rows[0]["run_id"]) == run_id
    assert rows[0]["account_name"] == account_name

    equity_rows = fetch_backtest_report_snapshots(conn, run_id)
    assert len(equity_rows) == 2
    assert float(equity_rows[0]["equity"]) == 1000.0
