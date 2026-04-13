import pytest

from trading.services.accounts_service import create_account, get_account
from trading.services.evaluation_service import fetch_strategy_evaluation


def _insert_backtest_run(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    run_name: str = "evaluation-smoke",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_name,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_name,
            run_name,
            "2026-01-01",
            "2026-01-31",
            "2026-02-01T00:00:00Z",
            5.0,
            0.0,
            "trading/config/trade_universe.txt",
            "seeded",
            "warning-a",
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _insert_backtest_snapshot(conn, *, run_id: int, snapshot_time: str, equity: float) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, equity, 0.0, equity, 0.0, 0.0),
    )


def _insert_backtest_trade(conn, *, run_id: int, trade_time: str) -> None:
    conn.execute(
        """
        INSERT INTO backtest_trades (
            run_id,
            trade_time,
            ticker,
            side,
            qty,
            price,
            fee,
            slippage_bps,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, "AAPL", "buy", 1.0, 100.0, 0.0, 5.0, "seeded"),
    )


def _insert_snapshot(
    conn,
    *,
    account_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl,
        ),
    )


def test_fetch_strategy_evaluation_assembles_backtest_and_snapshot_evidence(conn) -> None:
    create_account(conn, "acct_eval", "trend_v1", 1000.0, "SPY")
    account = get_account(conn, "acct_eval")

    run_id = _insert_backtest_run(conn, account_id=account["id"], strategy_name="trend_v1")
    _insert_backtest_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=1000.0)
    _insert_backtest_snapshot(conn, run_id=run_id, snapshot_time="2026-01-15T00:00:00Z", equity=1100.0)
    _insert_backtest_snapshot(conn, run_id=run_id, snapshot_time="2026-01-31T00:00:00Z", equity=1050.0)
    _insert_backtest_trade(conn, run_id=run_id, trade_time="2026-01-02T00:00:00Z")
    _insert_backtest_trade(conn, run_id=run_id, trade_time="2026-01-10T00:00:00Z")

    _insert_snapshot(
        conn,
        account_id=account["id"],
        snapshot_time="2026-02-01T00:00:00Z",
        cash=800.0,
        market_value=220.0,
        equity=1020.0,
        realized_pnl=10.0,
        unrealized_pnl=20.0,
    )
    conn.commit()

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval")

    assert artifact.basic.requested_strategy == "trend_v1"
    assert artifact.backtest.available is True
    assert artifact.backtest.run_id == run_id
    assert artifact.backtest.total_return_pct == pytest.approx(5.0)
    assert artifact.backtest.max_drawdown_pct == pytest.approx(-4.545454545454546)
    assert artifact.paper_live.available is True
    assert artifact.paper_live.source_level == "account_snapshot"
    assert artifact.paper_live.return_pct == pytest.approx(2.0)
    assert artifact.confidence.overall_confidence > 0.0
    assert artifact.confidence.blended_score is not None
    assert artifact.confidence.blended_score > artifact.paper_live.return_pct
    assert "walk_forward_grouping_not_persisted" in artifact.diagnostics.data_gaps


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
