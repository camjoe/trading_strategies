from __future__ import annotations

from trading.backtesting.repositories.history_repository import fetch_strategy_backtest_rows


def test_history_repository_fetches_rows_with_filters(bt_repo_account, seed_bt_run, conn) -> None:
    _account_name, account_id = bt_repo_account

    seed_bt_run(
        account_id,
        strategy_name="trend",
        run_name="trend-2026-02-01",
        created_at="2026-02-01T00:00:00Z",
        start_equity=1000.0,
        end_equity=1100.0,
        end_date="2026-02-01",
    )
    seed_bt_run(
        account_id,
        strategy_name="mean",
        run_name="mean-2026-02-10",
        created_at="2026-02-10T00:00:00Z",
        start_equity=1000.0,
        end_equity=900.0,
        end_date="2026-02-10",
    )

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
