from __future__ import annotations

import sqlite3


def seed_admin_db(conn: sqlite3.Connection) -> None:
    """Populate *conn* with the canonical admin test dataset.

    Inserts two accounts with associated orders and fills, equity snapshots,
    daily metrics, rotation decisions, backtest runs, walk-forward groups,
    promotion reviews and events, and risk telemetry.  Used by the
    ``seeded_conn`` fixture in ``conftest.py`` so that individual tests do not
    repeat this setup inline.
    """
    conn.executescript(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
        VALUES
            (1, 'acct_a', 'Trend', 1000, '2026-01-01T00:00:00Z'),
            (2, 'acct_b', 'Trend', 1500, '2026-01-01T00:00:00Z');

        INSERT INTO books (
            id, account_id, name, status, is_default, start_equity, current_cash,
            current_equity, created_at, updated_at
        )
        VALUES
            (1, 1, 'default', 'active', 1, 1000, 900, 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
            (2, 2, 'default', 'active', 1, 1500, 1300, 1500, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');

        INSERT INTO equity_snapshots (
            book_id, snapshot_time, cash, market_value, equity, realized_pnl,
            unrealized_pnl
        )
        VALUES
            (1, '2026-01-02T00:00:00Z', 900, 100, 1000, 0, 0),
            (2, '2026-01-02T00:00:00Z', 1300, 200, 1500, 0, 0);

        INSERT INTO daily_metrics (book_id, metric_date, created_at, updated_at)
        VALUES
            (1, '2026-01-02', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'),
            (2, '2026-01-02', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z');

        INSERT INTO rotation_decisions (
            book_id, decision_time, rotation_action, score_components_json,
            gate_results_json, created_at
        )
        VALUES
            (1, '2026-01-02T00:00:00Z', 'hold', '{}', '{}', '2026-01-02T00:00:00Z'),
            (2, '2026-01-02T00:00:00Z', 'hold', '{}', '{}', '2026-01-02T00:00:00Z');

        INSERT INTO orders (
            id, book_id, account_id, symbol, side, qty, status, submitted_at, updated_at
        )
        VALUES
            (501, 1, 1, 'SPY', 'buy', 1, 'filled', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'),
            (502, 2, 2, 'QQQ', 'buy', 2, 'filled', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z');

        INSERT INTO order_fills (order_id, exec_id, filled_qty, fill_price, fill_time)
        VALUES
            (501, 'exec-a', 1, 100, '2026-01-02T00:00:00Z'),
            (502, 'exec-b', 2, 200, '2026-01-02T00:00:00Z');

        INSERT INTO risk_snapshots (
            account_id, snapshot_time, gross_exposure, net_exposure,
            max_symbol_concentration_pct, max_sector_concentration_pct, risk_payload_json
        )
        VALUES
            (1, '2026-01-02T00:00:00Z', 100, 100, 10, 20, '{}'),
            (2, '2026-01-02T00:00:00Z', 200, 200, 10, 20, '{}');

        INSERT INTO risk_decisions (
            account_id, book_id, decision_time, action, reason_code, risk_payload_json, created_at
        )
        VALUES
            (1, 1, '2026-01-02T00:00:00Z', 'allow', 'within_limits', '{}', '2026-01-02T00:00:00Z'),
            (2, 2, '2026-01-02T00:00:00Z', 'allow', 'within_limits', '{}', '2026-01-02T00:00:00Z');

        -- strategy_id left NULL: reads fall back to the account strategy ('Trend').
        INSERT INTO backtest_runs (id, account_id, run_name, start_date, end_date, created_at)
        VALUES
            (11, 1, 'run_a', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z'),
            (22, 2, 'run_b', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z');

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
            id, grouping_key, account_id, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, average_return_pct, median_return_pct,
            best_return_pct, worst_return_pct, created_at
        )
        VALUES
            (
                301, 'acct_a_wf', 1, 'wf_a', '2025-01-01', '2025-06-01',
                1, 1, 1, 2.0, 2.0, 2.0, 2.0, '2026-01-03T00:00:00Z'
            ),
            (
                302, 'acct_b_wf', 2, 'wf_b', '2025-01-01', '2025-06-01',
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


__all__ = [
    "seed_admin_db",
]
