from __future__ import annotations

import sqlite3
from collections.abc import Callable

from common.time import utc_now_iso
from paper_trading_ui.backend.routes.accounts import api_account_detail, api_accounts_compare


def test_account_detail_exposes_latest_backtest_summary(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(conn, "acct_api_latest", initial_cash=10000.0)
    acct = conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_api_latest",)).fetchone()
    assert acct is not None

    conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            run_name,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            tickers_file,
            notes,
            warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(acct["id"]),
            "latest-run",
            "2026-01-01",
            "2026-01-31",
            utc_now_iso(),
            5.0,
            0.0,
            "trading/config/trade_universe.txt",
            "seed test run",
            "daily bars only",
        ),
    )
    conn.commit()

    payload = api_account_detail("acct_api_latest")

    assert payload["account"]["accountKind"] == "managed"
    assert payload["account"]["brokerType"] == "paper"
    latest = payload["latestBacktest"]
    assert latest is not None
    assert latest["accountName"] == "acct_api_latest"
    assert latest["runName"] == "latest-run"


def test_accounts_compare_endpoint(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(conn, "acct_cmp_a", strategy="trend")
    create_route_test_account(conn, "acct_cmp_b", strategy="mean_reversion")

    payload = api_accounts_compare()

    names = {item["name"] for item in payload["accounts"]}
    assert "acct_cmp_a" in names
    assert "acct_cmp_b" in names
