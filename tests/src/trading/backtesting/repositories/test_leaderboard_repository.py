from __future__ import annotations

from trading.backtesting.repositories.leaderboard_repository import fetch_equity_rows, fetch_leaderboard_rows


def test_leaderboard_repository_fetches_rows_and_equity_curve(conn, bt_repo_account, seed_bt_run) -> None:
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

    equity_rows = fetch_equity_rows(conn, run_id)
    assert len(equity_rows) == 2
    assert float(equity_rows[0]["equity"]) == 1000.0
