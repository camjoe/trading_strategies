from __future__ import annotations

from trading.accounts import create_account
from trading.backtesting.repositories.leaderboard_repository import fetch_equity_rows, fetch_leaderboard_rows


def _seed_run(conn, *, account_id: int, strategy_name: str, run_name: str, created_at: str) -> int:
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
                run_name,
                "2026-01-01",
                "2026-01-31",
                created_at,
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
            1000.0,
            0.0,
            1000.0,
            0.0,
            0.0,
            run_id,
            "2026-01-31T00:00:00Z",
            1100.0,
            0.0,
            1100.0,
            0.0,
            0.0,
        ),
    )
    conn.execute(
        """
        INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-15", "AAPL", "buy", 1.0, 100.0, 0.0, 0.0, "test"),
    )
    conn.commit()
    return run_id


def test_leaderboard_repository_fetches_rows_and_equity_curve(conn) -> None:
    create_account(conn, "acct_lb_repo", "trend", 10000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_lb_repo",)).fetchone()["id"])

    run_id = _seed_run(
        conn,
        account_id=account_id,
        strategy_name="trend",
        run_name="lb-run",
        created_at="2026-02-01T00:00:00Z",
    )

    rows = fetch_leaderboard_rows(
        conn,
        limit=10,
        account_name="acct_lb_repo",
        strategy="trend",
    )

    assert len(rows) == 1
    assert int(rows[0]["run_id"]) == run_id
    assert rows[0]["account_name"] == "acct_lb_repo"

    equity_rows = fetch_equity_rows(conn, run_id)
    assert len(equity_rows) == 2
    assert float(equity_rows[0]["equity"]) == 1000.0
