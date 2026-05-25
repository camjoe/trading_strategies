from __future__ import annotations

import pytest

from trading.backtesting.services.walk_forward_report_service import fetch_walk_forward_report_data
from trading.services.accounts import create_account


def test_fetch_walk_forward_report_data_by_group_id(conn) -> None:
    conn.executescript(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_a', 'Trend', 1000, 'SPY', '2026-01-01T00:00:00Z');

        INSERT INTO backtest_runs (
            id, account_id, strategy_name, run_name, start_date, end_date, slippage_bps,
            fee_per_trade, tickers_file, notes, warnings, created_at
        )
        VALUES
            (
                11, 1, 'Trend', 'wf_01', '2026-01-01', '2026-01-31', 5.0, 0.0,
                'tickers.txt', '', '', '2026-02-01T00:00:00Z'
            ),
            (
                12, 1, 'Trend', 'wf_02', '2026-02-01', '2026-02-28', 5.0, 0.0,
                'tickers.txt', '', '', '2026-03-01T00:00:00Z'
            );

        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES
            (11, '2026-01-01T00:00:00Z', 1000, 0, 1000, 0, 0),
            (11, '2026-01-31T00:00:00Z', 1000, 20, 1020, 0, 20),
            (12, '2026-02-01T00:00:00Z', 1000, 0, 1000, 0, 0),
            (12, '2026-02-28T00:00:00Z', 1000, -10, 990, 0, -10);

        INSERT INTO walk_forward_groups (
            id, grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, average_return_pct, median_return_pct,
            best_return_pct, worst_return_pct, created_at
        )
        VALUES (
            7, 'wf-group-1', 1, 'Trend', 'wf', '2026-01-01', '2026-02-28',
            1, 1, 2, 0.5, 0.5, 2.0, -1.0, '2026-03-15T00:00:00Z'
        );

        INSERT INTO walk_forward_group_runs (
            group_id, run_id, window_index, window_start, window_end, total_return_pct
        )
        VALUES
            (7, 11, 1, '2026-01-01', '2026-01-31', 2.0),
            (7, 12, 2, '2026-02-01', '2026-02-28', -1.0);
        """
    )
    conn.commit()

    report = fetch_walk_forward_report_data(conn, group_id=7)

    assert report.group_id == 7
    assert report.strategy_name == "Trend"
    assert report.window_count == 2
    assert [item.window_index for item in report.windows] == [1, 2]
    assert report.windows[0].backtest_summary.run_name == "wf_01"
    assert report.windows[1].backtest_summary.trade_count == 0


def test_fetch_walk_forward_report_data_by_latest_account(conn) -> None:
    conn.executescript(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_a', 'Trend', 1000, 'SPY', '2026-01-01T00:00:00Z');

        INSERT INTO backtest_runs (
            id, account_id, strategy_name, run_name, start_date, end_date, slippage_bps,
            fee_per_trade, tickers_file, notes, warnings, created_at
        )
        VALUES (
            11, 1, 'Trend', 'wf_01', '2026-01-01', '2026-01-31', 5.0, 0.0,
            'tickers.txt', '', '', '2026-02-01T00:00:00Z'
        );

        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES
            (11, '2026-01-01T00:00:00Z', 1000, 0, 1000, 0, 0),
            (11, '2026-01-31T00:00:00Z', 1000, 30, 1030, 0, 30);

        INSERT INTO walk_forward_groups (
            id, grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, average_return_pct, median_return_pct,
            best_return_pct, worst_return_pct, created_at
        )
        VALUES (
            9, 'wf-group-9', 1, 'Trend', 'wf', '2026-01-01', '2026-01-31',
            1, 1, 1, 3.0, 3.0, 3.0, 3.0, '2026-03-15T00:00:00Z'
        );

        INSERT INTO walk_forward_group_runs (
            group_id, run_id, window_index, window_start, window_end, total_return_pct
        )
        VALUES (9, 11, 1, '2026-01-01', '2026-01-31', 3.0);
        """
    )
    conn.commit()

    report = fetch_walk_forward_report_data(conn, account_name="acct_a")

    assert report.group_id == 9
    assert report.account_name == "acct_a"
    assert report.windows[0].backtest_summary.run_id == 11


# ---------------------------------------------------------------------------
# _resolve_walk_forward_group: error paths
# ---------------------------------------------------------------------------


def test_group_id_not_found_raises_value_error(conn) -> None:
    """Requesting a non-existent group_id raises ValueError (line 27)."""
    with pytest.raises(ValueError, match="not found"):
        fetch_walk_forward_report_data(conn, group_id=99999)


def test_neither_group_id_nor_account_name_raises_value_error(conn) -> None:
    """Calling without group_id or account_name raises ValueError (line 31)."""
    with pytest.raises(ValueError, match="group-id or --account"):
        fetch_walk_forward_report_data(conn)


def test_no_walk_forward_groups_for_account_raises_value_error(conn) -> None:
    """Account exists but has no walk-forward groups → ValueError (lines 44-45)."""
    create_account(conn, "acct_wf_empty", "trend", 1_000.0, "SPY")
    conn.commit()

    with pytest.raises(ValueError, match="No walk-forward groups found for account"):
        fetch_walk_forward_report_data(conn, account_name="acct_wf_empty")


def test_no_walk_forward_groups_for_account_and_strategy_raises_value_error(conn) -> None:
    """Account exists but has no groups for the given strategy → ValueError (lines 38, 46)."""
    create_account(conn, "acct_wf_no_strat", "trend", 1_000.0, "SPY")
    conn.commit()

    with pytest.raises(ValueError, match="No walk-forward groups found for account"):
        fetch_walk_forward_report_data(conn, account_name="acct_wf_no_strat", strategy_name="NonExistentV99")


def test_fetch_walk_forward_report_data_by_account_and_strategy(conn) -> None:
    """Fetching by account_name + strategy_name uses the strategy branch (line 38) and succeeds."""
    conn.executescript(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (50, 'acct_wf_strat', 'Trend', 1000, 'SPY', '2026-01-01T00:00:00Z');

        INSERT INTO backtest_runs (
            id, account_id, strategy_name, run_name, start_date, end_date, slippage_bps,
            fee_per_trade, tickers_file, notes, warnings, created_at
        ) VALUES (
            50, 50, 'Trend', 'wf_s01', '2026-01-01', '2026-01-31', 5.0, 0.0,
            'tickers.txt', '', '', '2026-02-01T00:00:00Z'
        );

        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        ) VALUES
            (50, '2026-01-01T00:00:00Z', 1000, 0, 1000, 0, 0),
            (50, '2026-01-31T00:00:00Z', 1000, 10, 1010, 0, 10);

        INSERT INTO walk_forward_groups (
            id, grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, average_return_pct, median_return_pct,
            best_return_pct, worst_return_pct, created_at
        ) VALUES (
            50, 'wf-strat-key', 50, 'Trend', 'wf_s', '2026-01-01', '2026-01-31',
            1, 1, 1, 1.0, 1.0, 1.0, 1.0, '2026-03-15T00:00:00Z'
        );

        INSERT INTO walk_forward_group_runs (
            group_id, run_id, window_index, window_start, window_end, total_return_pct
        ) VALUES (50, 50, 1, '2026-01-01', '2026-01-31', 1.0);
        """
    )
    conn.commit()

    report = fetch_walk_forward_report_data(conn, account_name="acct_wf_strat", strategy_name="Trend")

    assert report.group_id == 50
    assert report.strategy_name == "Trend"
    assert len(report.windows) == 1
