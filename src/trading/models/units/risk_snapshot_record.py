from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float


@dataclass(frozen=True, slots=True)
class RiskSnapshotRecord:
    """Persisted risk_snapshots row materialized from the database."""

    id: int
    account_id: int
    snapshot_time: str
    gross_exposure: float
    net_exposure: float
    max_symbol_concentration_pct: float
    max_sector_concentration_pct: float
    drawdown_pct: float | None
    leverage_proxy: float | None
    daily_loss_pct: float | None
    kill_switch_triggered: int
    risk_payload_json: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RiskSnapshotRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            snapshot_time=row_expect_str(values, "snapshot_time"),
            gross_exposure=row_expect_float(values, "gross_exposure"),
            net_exposure=row_expect_float(values, "net_exposure"),
            max_symbol_concentration_pct=row_expect_float(values, "max_symbol_concentration_pct"),
            max_sector_concentration_pct=row_expect_float(values, "max_sector_concentration_pct"),
            drawdown_pct=row_float(values, "drawdown_pct"),
            leverage_proxy=row_float(values, "leverage_proxy"),
            daily_loss_pct=row_float(values, "daily_loss_pct"),
            kill_switch_triggered=row_expect_int(values, "kill_switch_triggered"),
            risk_payload_json=row_expect_str(values, "risk_payload_json"),
        )
