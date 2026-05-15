from __future__ import annotations

from trading.database.db_init import ensure_db


def seed_admin_dataset() -> None:
    conn = ensure_db()
    try:
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
            VALUES
                (1, 'acct_a', 'Trend', 1000, '2026-01-01T00:00:00Z'),
                (2, 'acct_b', 'Trend', 1500, '2026-01-01T00:00:00Z');

            INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
            VALUES
                (1, 'SPY', 'buy', 1, 100, 0, '2026-01-02T00:00:00Z', ''),
                (2, 'QQQ', 'buy', 2, 200, 0, '2026-01-02T00:00:00Z', '');

            INSERT INTO equity_snapshots (
                account_id, snapshot_time, cash, market_value, equity, realized_pnl,
                unrealized_pnl
            )
            VALUES
                (1, '2026-01-02T00:00:00Z', 900, 100, 1000, 0, 0),
                (2, '2026-01-02T00:00:00Z', 1300, 200, 1500, 0, 0);

            INSERT INTO backtest_runs (id, account_id, strategy_name, run_name, start_date, end_date, created_at)
            VALUES
                (11, 1, 'Trend', 'run_a', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z'),
                (22, 2, 'Trend', 'run_b', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z');

            INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note)
            VALUES
                (11, '2025-01-10T00:00:00Z', 'SPY', 'buy', 1, 100, 0, 0, ''),
                (22, '2025-01-10T00:00:00Z', 'QQQ', 'buy', 1, 200, 0, 0, '');

            INSERT INTO backtest_equity_snapshots (
                run_id, snapshot_time, cash, market_value, equity, realized_pnl,
                unrealized_pnl
            )
            VALUES
                (11, '2025-01-10T00:00:00Z', 900, 100, 1000, 0, 0),
                (22, '2025-01-10T00:00:00Z', 1300, 200, 1500, 0, 0);

            INSERT INTO walk_forward_groups (
                id, grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
                test_months, step_months, window_count, average_return_pct, median_return_pct,
                best_return_pct, worst_return_pct, created_at
            )
            VALUES
                (
                    301, 'acct_a_wf', 1, 'Trend', 'wf_a', '2025-01-01', '2025-06-01',
                    1, 1, 1, 2.0, 2.0, 2.0, 2.0, '2026-01-03T00:00:00Z'
                ),
                (
                    302, 'acct_b_wf', 2, 'Trend', 'wf_b', '2025-01-01', '2025-06-01',
                    1, 1, 1, 3.0, 3.0, 3.0, 3.0, '2026-01-03T00:00:00Z'
                );

            INSERT INTO walk_forward_group_runs (
                group_id, run_id, window_index, window_start, window_end, total_return_pct
            )
            VALUES
                (301, 11, 1, '2025-01-01', '2025-06-01', 2.0),
                (302, 22, 1, '2025-01-01', '2025-06-01', 3.0);

            INSERT INTO promotion_reviews (
                id, account_id, account_name_snapshot, strategy_name, review_state,
                assessment_stage, assessment_status, ready_for_live, overall_confidence,
                live_trading_enabled_snapshot, promotion_assessment_version, evaluation_artifact_version,
                frozen_assessment_payload, frozen_evaluation_payload,
                requested_by, operator_summary_note, created_at, updated_at
            )
            VALUES
                (
                    101, 1, 'acct_a', 'Trend', 'requested',
                    'promotion_review', 'ready_for_review', 1, 0.75,
                    0, 'phase3.v1', 'phase2.v1',
                    '{"status":"ready_for_review"}', '{"basic":{"account_name":"acct_a"}}',
                    'alice', 'initial request', '2026-01-04T00:00:00Z', '2026-01-04T00:00:00Z'
                ),
                (
                    202, 2, 'acct_b', 'Trend', 'requested',
                    'promotion_review', 'ready_for_review', 1, 0.70,
                    0, 'phase3.v1', 'phase2.v1',
                    '{"status":"ready_for_review"}', '{"basic":{"account_name":"acct_b"}}',
                    'bob', 'initial request', '2026-01-04T00:00:00Z', '2026-01-04T00:00:00Z'
                );

            INSERT INTO promotion_review_events (
                review_id, event_seq, event_type, actor_type, actor_name,
                from_review_state, to_review_state, note, event_payload, created_at
            )
            VALUES
                (
                    101, 1, 'requested', 'operator', 'alice', NULL, 'requested',
                    'initial request', '{}', '2026-01-04T00:00:00Z'
                ),
                (
                    202, 1, 'requested', 'operator', 'bob', NULL, 'requested',
                    'initial request', '{}', '2026-01-04T00:00:00Z'
                );
            """
        )
        conn.commit()
    finally:
        conn.close()


__all__ = [
    "seed_admin_dataset",
]
