from __future__ import annotations

import sqlite3

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_str
from trading.backtesting.report_models import BacktestReportSummary, WalkForwardDetailReport, WalkForwardWindowDetail
from trading.backtesting.repositories.walk_forward_repository import (
    fetch_latest_walk_forward_group_for_account,
    fetch_latest_walk_forward_group_for_account_strategy,
    fetch_walk_forward_group_by_id,
    fetch_walk_forward_group_runs,
)
from trading.backtesting.services.report_service import fetch_backtest_report_summary
from trading.repositories.accounts_repository import fetch_account_by_name


def _resolve_walk_forward_group(
    conn: sqlite3.Connection,
    *,
    group_id: int | None,
    account_name: str | None,
    strategy_name: str | None,
) -> sqlite3.Row:
    if group_id is not None:
        group = fetch_walk_forward_group_by_id(conn, group_id=group_id)
        if group is None:
            raise ValueError(f"Walk-forward group {group_id} not found.")
        return group

    if account_name is None:
        raise ValueError("Provide either --group-id or --account.")

    account = fetch_account_by_name(conn, account_name)
    if account is None:
        raise ValueError(f"Account '{account_name}' not found.")

    if strategy_name is None:
        group = fetch_latest_walk_forward_group_for_account(conn, account_id=int(account["id"]))
    else:
        group = fetch_latest_walk_forward_group_for_account_strategy(
            conn,
            account_id=int(account["id"]),
            strategy_name=strategy_name,
        )
    if group is None:
        if strategy_name is None:
            raise ValueError(f"No walk-forward groups found for account '{account_name}'.")
        raise ValueError(
            f"No walk-forward groups found for account '{account_name}' and strategy '{strategy_name}'."
        )
    return group


def fetch_walk_forward_report_data(
    conn: sqlite3.Connection,
    *,
    group_id: int | None = None,
    account_name: str | None = None,
    strategy_name: str | None = None,
) -> WalkForwardDetailReport:
    group = _resolve_walk_forward_group(
        conn,
        group_id=group_id,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    group_runs = fetch_walk_forward_group_runs(conn, group_id=row_expect_int(group, "id"))
    windows = [
        WalkForwardWindowDetail(
            window_index=row_expect_int(item, "window_index"),
            window_start=row_expect_str(item, "window_start"),
            window_end=row_expect_str(item, "window_end"),
            total_return_pct=row_expect_float(item, "total_return_pct"),
            backtest_summary=BacktestReportSummary.from_mapping(
                fetch_backtest_report_summary(conn, row_expect_int(item, "run_id")).__dict__
            ),
        )
        for item in group_runs
    ]
    return WalkForwardDetailReport(
        group_id=row_expect_int(group, "id"),
        account_name=account_name or windows[0].backtest_summary.account_name if windows else account_name or "",
        strategy_name=row_expect_str(group, "strategy_name"),
        run_name_prefix=row_str(group, "run_name_prefix"),
        start_date=row_expect_str(group, "start_date"),
        end_date=row_expect_str(group, "end_date"),
        test_months=row_expect_int(group, "test_months"),
        step_months=row_expect_int(group, "step_months"),
        window_count=row_expect_int(group, "window_count"),
        average_return_pct=row_expect_float(group, "average_return_pct"),
        median_return_pct=row_expect_float(group, "median_return_pct"),
        best_return_pct=row_expect_float(group, "best_return_pct"),
        worst_return_pct=row_expect_float(group, "worst_return_pct"),
        created_at=row_expect_str(group, "created_at"),
        windows=windows,
    )
