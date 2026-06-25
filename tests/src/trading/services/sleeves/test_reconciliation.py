from __future__ import annotations

import pytest

from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.sleeves.reconciliation import (
    reconcile_sleeves_vs_account_equity,
    reconcile_sleeves_vs_latest_snapshot,
)
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


def _insert_sleeve(
    conn,
    *,
    account_id: int,
    name: str,
    equity: float,
) -> int:
    return insert_test_sleeve(
        conn,
        account_id=account_id,
        name=name,
        start_equity=equity,
        current_cash=equity,
        current_equity=equity,
    )


def test_reconcile_sleeves_vs_account_equity_pass_and_fail(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_recon")
    _insert_sleeve(conn, account_id=account_id, name="a", equity=4_000.0)
    _insert_sleeve(conn, account_id=account_id, name="b", equity=6_000.0)

    pass_result = reconcile_sleeves_vs_account_equity(
        conn,
        account_id=account_id,
        account_equity=10_000.005,
        tolerance=0.01,
    )
    fail_result = reconcile_sleeves_vs_account_equity(
        conn,
        account_id=account_id,
        account_equity=9_950.0,
        tolerance=0.01,
    )

    assert pass_result.within_tolerance is True
    assert pass_result.equity_difference == pytest.approx(-0.005)
    assert fail_result.within_tolerance is False
    assert fail_result.equity_difference == pytest.approx(50.0)


def test_reconcile_sleeves_vs_latest_snapshot_uses_latest_equity(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_recon_snapshot")
    _insert_sleeve(conn, account_id=account_id, name="a", equity=5_000.0)
    _insert_sleeve(conn, account_id=account_id, name="b", equity=5_000.0)

    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time="2026-05-03T12:00:00Z",
        cash=2_000.0,
        market_value=8_000.0,
        equity=10_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )

    result = reconcile_sleeves_vs_latest_snapshot(conn, account_id=account_id, tolerance=0.01)
    assert result.within_tolerance is True
    assert result.snapshot_time == "2026-05-03T12:00:00Z"


def test_reconcile_sleeves_vs_latest_snapshot_requires_snapshot(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_recon_missing_snapshot")
    _insert_sleeve(conn, account_id=account_id, name="a", equity=1_000.0)

    with pytest.raises(ValueError, match="No equity snapshot available"):
        reconcile_sleeves_vs_latest_snapshot(conn, account_id=account_id)
