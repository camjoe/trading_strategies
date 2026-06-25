from __future__ import annotations

import pytest

from trading.services.accounts import create_account, get_account
from trading.services.reporting.backtest_returns import fetch_strategy_backtest_returns


def test_returns_rows_for_selected_strategies_within_date_range(conn, seed_history_run) -> None:
    create_account(conn, "acct", "trend", 10000.0, "SPY")
    account = get_account(conn, "acct")
    assert account is not None

    seed_history_run(
        int(account["id"]),
        strategy_name="trend",
        end_date="2026-03-08",
        start_equity=10000.0,
        end_equity=10500.0,
    )
    seed_history_run(
        int(account["id"]),
        strategy_name="mean_reversion",
        end_date="2026-03-15",
        start_equity=10000.0,
        end_equity=11000.0,
    )

    out = fetch_strategy_backtest_returns(
        conn,
        account_id=int(account["id"]),
        strategy_names=["trend", "mean_reversion"],
        start_day="2026-03-01",
        end_day="2026-03-31",
    )

    assert [name for name, _ret in out] == ["mean_reversion", "trend"]
    assert out[0][1] == pytest.approx(10.0)
    assert out[1][1] == pytest.approx(5.0)


def test_skips_rows_with_invalid_equity_values(conn, seed_history_run) -> None:
    create_account(conn, "acct", "trend", 10000.0, "SPY")
    account = get_account(conn, "acct")
    assert account is not None

    seed_history_run(
        int(account["id"]),
        strategy_name="trend",
        end_date="2026-03-08",
        start_equity=0.0,
        end_equity=1000.0,
    )

    out = fetch_strategy_backtest_returns(
        conn,
        account_id=int(account["id"]),
        strategy_names=["trend"],
        start_day="2026-03-01",
        end_day="2026-03-31",
    )

    assert out == []
