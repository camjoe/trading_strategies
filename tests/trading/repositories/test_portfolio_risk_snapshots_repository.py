from __future__ import annotations

from trading.repositories.portfolio_risk_snapshots import PortfolioRiskSnapshotRepository
from tests.support.repositories import insert_repository_account


def _account_id(conn, name: str = "risk_acct") -> int:
    return insert_repository_account(conn, name=name)


def _upsert(
    conn,
    *,
    account_id: int,
    snapshot_time: str,
    gross_exposure: float = 1000.0,
    kill_switch_triggered: int = 0,
) -> None:
    PortfolioRiskSnapshotRepository(conn).upsert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        gross_exposure=gross_exposure,
        net_exposure=500.0,
        max_symbol_concentration_pct=0.2,
        max_sector_concentration_pct=0.4,
        drawdown_pct=None,
        leverage_proxy=None,
        daily_loss_pct=None,
        kill_switch_triggered=kill_switch_triggered,
        risk_payload_json="{}",
    )


class TestUpsert:
    def test_insert_is_fetchable(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=2000.0)
        row = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.gross_exposure == 2000.0

    def test_conflict_updates_existing_row(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=1000.0)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=9999.0)
        row = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.gross_exposure == 9999.0

    def test_conflict_does_not_create_duplicate(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z")
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z")
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM portfolio_risk_snapshots WHERE account_id = ?", (acct_id,)
        ).fetchone()["n"]
        assert count == 1

    def test_nullable_fields_stored_as_null(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z")
        row = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.drawdown_pct is None
        assert row.leverage_proxy is None
        assert row.daily_loss_pct is None


class TestFetchLatest:
    def test_returns_none_when_no_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)
        assert PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id) is None

    def test_returns_most_recent_by_snapshot_time(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T09:00:00Z", gross_exposure=100.0)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T11:00:00Z", gross_exposure=200.0)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=150.0)
        row = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.gross_exposure == 200.0

    def test_isolated_per_account(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _upsert(conn, account_id=acct_a, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=111.0)
        _upsert(conn, account_id=acct_b, snapshot_time="2026-01-01T10:00:00Z", gross_exposure=222.0)
        assert PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_a).gross_exposure == 111.0
        assert PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_b).gross_exposure == 222.0

    def test_kill_switch_stored_and_retrieved(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, snapshot_time="2026-01-01T10:00:00Z", kill_switch_triggered=1)
        row = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.kill_switch_triggered is True
