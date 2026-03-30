from __future__ import annotations

from trading.accounts import create_account
from trading.backtesting.repositories.history_repository import fetch_strategy_backtest_rows


def _seed_run(conn, *, account_id: int, strategy_name: str, end_date: str, start_eq: float, end_eq: float) -> int:
    run_id = int(
        conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id, strategy_name, run_name, start_date, end_date,
                created_at, slippage_bps, fee_per_trade, tickers_file, notes, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                strategy_name,
                f"{strategy_name}-{end_date}",
                "2026-01-01",
                end_date,
                f"{end_date}T00:00:00Z",
                0.0,
                0.0,
                "trading/config/trade_universe.txt",
                "",
                "",
            ),
        ).lastrowid
    )
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-01-01T00:00:00Z",
            start_eq,
            0.0,
            start_eq,
            0.0,
            0.0,
            run_id,
            f"{end_date}T00:00:00Z",
            end_eq,
            0.0,
            end_eq,
            0.0,
            0.0,
        ),
    )
    conn.commit()
    return run_id


def test_history_repository_fetches_rows_with_filters(conn) -> None:
    create_account(conn, "acct_hist", "trend_v1", 10000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_hist",)).fetchone()["id"])

    _seed_run(conn, account_id=account_id, strategy_name="trend", end_date="2026-02-01", start_eq=1000.0, end_eq=1100.0)
    _seed_run(conn, account_id=account_id, strategy_name="mean", end_date="2026-02-10", start_eq=1000.0, end_eq=900.0)

    rows = fetch_strategy_backtest_rows(
        conn,
        account_id=account_id,
        strategy_names=["trend"],
        start_day="2026-01-01",
        end_day="2026-03-01",
    )

    assert len(rows) == 1
    assert rows[0]["strategy_name"] == "trend"
    assert float(rows[0]["starting_equity"]) == 1000.0
    assert float(rows[0]["ending_equity"]) == 1100.0
