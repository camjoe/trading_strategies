from __future__ import annotations

import sqlite3

from trading.models.portfolio.portfolio_risk_snapshot_record import PortfolioRiskSnapshotRecord


class PortfolioRiskSnapshotRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> PortfolioRiskSnapshotRecord:
        return PortfolioRiskSnapshotRecord.from_mapping(dict(row))

    def upsert(
        self,
        *,
        account_id: int,
        snapshot_time: str,
        gross_exposure: float,
        net_exposure: float,
        max_symbol_concentration_pct: float,
        max_sector_concentration_pct: float,
        drawdown_pct: float | None,
        leverage_proxy: float | None,
        daily_loss_pct: float | None,
        kill_switch_triggered: int,
        risk_payload_json: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO portfolio_risk_snapshots (
                account_id,
                snapshot_time,
                gross_exposure,
                net_exposure,
                max_symbol_concentration_pct,
                max_sector_concentration_pct,
                drawdown_pct,
                leverage_proxy,
                daily_loss_pct,
                kill_switch_triggered,
                risk_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, snapshot_time)
            DO UPDATE SET
                gross_exposure = excluded.gross_exposure,
                net_exposure = excluded.net_exposure,
                max_symbol_concentration_pct = excluded.max_symbol_concentration_pct,
                max_sector_concentration_pct = excluded.max_sector_concentration_pct,
                drawdown_pct = excluded.drawdown_pct,
                leverage_proxy = excluded.leverage_proxy,
                daily_loss_pct = excluded.daily_loss_pct,
                kill_switch_triggered = excluded.kill_switch_triggered,
                risk_payload_json = excluded.risk_payload_json
            """,
            (
                int(account_id),
                snapshot_time,
                float(gross_exposure),
                float(net_exposure),
                float(max_symbol_concentration_pct),
                float(max_sector_concentration_pct),
                None if drawdown_pct is None else float(drawdown_pct),
                None if leverage_proxy is None else float(leverage_proxy),
                None if daily_loss_pct is None else float(daily_loss_pct),
                int(kill_switch_triggered),
                risk_payload_json,
            ),
        )
        self._conn.commit()

    def fetch_latest(self, *, account_id: int) -> PortfolioRiskSnapshotRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM portfolio_risk_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT 1
            """,
            (int(account_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None
