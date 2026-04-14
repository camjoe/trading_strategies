from __future__ import annotations

from trading.backtesting.services.walk_forward_report_service import fetch_walk_forward_report_data


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
            (11, 1, 'Trend', 'wf_01', '2026-01-01', '2026-01-31', 5.0, 0.0, 'tickers.txt', '', '', '2026-02-01T00:00:00Z'),
            (12, 1, 'Trend', 'wf_02', '2026-02-01', '2026-02-28', 5.0, 0.0, 'tickers.txt', '', '', '2026-03-01T00:00:00Z');

        INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
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

        INSERT INTO walk_forward_group_runs (group_id, run_id, window_index, window_start, window_end, total_return_pct)
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
        VALUES (11, 1, 'Trend', 'wf_01', '2026-01-01', '2026-01-31', 5.0, 0.0, 'tickers.txt', '', '', '2026-02-01T00:00:00Z');

        INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
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

        INSERT INTO walk_forward_group_runs (group_id, run_id, window_index, window_start, window_end, total_return_pct)
        VALUES (9, 11, 1, '2026-01-01', '2026-01-31', 3.0);
        """
    )
    conn.commit()

    report = fetch_walk_forward_report_data(conn, account_name="acct_a")

    assert report.group_id == 9
    assert report.account_name == "acct_a"
    assert report.windows[0].backtest_summary.run_id == 11
