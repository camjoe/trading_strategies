from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class SleeveRiskDecisionRecord:
    """Persisted sleeve_risk_decisions row materialized from the database."""

    id: int
    account_id: int
    sleeve_id: int | None
    decision_time: str
    symbol: str | None
    side: str | None
    action: str
    reason_code: str
    requested_qty: int | None
    approved_qty: int | None
    requested_notional: float | None
    approved_notional: float | None
    execution_mode: str
    risk_payload_json: str
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveRiskDecisionRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            sleeve_id=row_int(values, "sleeve_id"),
            decision_time=row_expect_str(values, "decision_time"),
            symbol=row_str(values, "symbol"),
            side=row_str(values, "side"),
            action=row_expect_str(values, "action"),
            reason_code=row_expect_str(values, "reason_code"),
            requested_qty=row_int(values, "requested_qty"),
            approved_qty=row_int(values, "approved_qty"),
            requested_notional=row_float(values, "requested_notional"),
            approved_notional=row_float(values, "approved_notional"),
            execution_mode=row_expect_str(values, "execution_mode"),
            risk_payload_json=row_expect_str(values, "risk_payload_json"),
            created_at=row_expect_str(values, "created_at"),
        )
