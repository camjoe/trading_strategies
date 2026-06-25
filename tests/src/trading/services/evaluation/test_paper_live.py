import pytest

from trading.services.accounts import create_account, get_account
from trading.services.evaluation import fetch_strategy_evaluation


def test_fetch_strategy_evaluation_uses_closed_rotation_episode_for_inactive_strategy(conn) -> None:
    create_account(conn, "acct_rotation_eval", "trend_v1", 1000.0, "SPY")
    conn.execute(
        """
        UPDATE accounts
        SET rotation_enabled = 1,
            rotation_schedule = '["trend_v1","mean_reversion"]',
            rotation_active_strategy = 'trend_v1'
        WHERE name = 'acct_rotation_eval'
        """
    )
    account = get_account(conn, "acct_rotation_eval")
    conn.execute(
        """
        INSERT INTO rotation_episodes (
            account_id,
            strategy_name,
            started_at,
            ended_at,
            starting_equity,
            ending_equity,
            starting_realized_pnl,
            ending_realized_pnl,
            realized_pnl_delta,
            snapshot_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account["id"],
            "mean_reversion",
            "2026-02-01T00:00:00Z",
            "2026-02-10T00:00:00Z",
            1000.0,
            1040.0,
            0.0,
            15.0,
            15.0,
            4,
        ),
    )
    conn.commit()

    artifact = fetch_strategy_evaluation(
        conn,
        account_name="acct_rotation_eval",
        strategy_name="mean_reversion",
    )

    assert artifact.paper_live.available is True
    assert artifact.paper_live.source_level == "rotation_episode_closed"
    assert artifact.paper_live.strategy_isolated is True
    assert artifact.paper_live.latest_equity == pytest.approx(1040.0)
    assert artifact.paper_live.return_pct == pytest.approx(4.0)


def test_fetch_strategy_evaluation_reports_data_gaps_when_evidence_missing(conn) -> None:
    create_account(conn, "acct_eval_empty", "trend_v1", 1000.0, "SPY")

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_empty")

    assert artifact.backtest.available is False
    assert artifact.paper_live.available is False
    assert artifact.walk_forward.available is False
    assert artifact.diagnostics.data_gaps == [
        "missing_backtest_evidence",
        "missing_paper_live_evidence",
        "walk_forward_grouping_not_persisted",
    ]
