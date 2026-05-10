"""Sleeve-mode risk persistence helpers for runtime auto-trading."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from common.time import parse_utc_iso
from trading.services.sleeves.risk_gate import DEFAULT_SYMBOL_SECTOR_MAP, resolve_sector_for_symbol


def compute_current_exposure_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    fetch_sleeve_positions_for_account_fn: Callable[..., list[Any]],
    fetch_strategy_sleeves_for_account_fn: Callable[..., list[Any]],
) -> tuple[float, float, float, float]:
    position_rows = fetch_sleeve_positions_for_account_fn(conn, account_id=account_id)
    gross_exposure = 0.0
    net_exposure = 0.0
    symbol_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    for row in position_rows:
        symbol = str(row["symbol"]).upper().strip()
        market_value = float(row["market_value"])
        abs_value = abs(market_value)
        gross_exposure += abs_value
        net_exposure += market_value
        symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + abs_value
        sector = resolve_sector_for_symbol(symbol, symbol_sector_map=DEFAULT_SYMBOL_SECTOR_MAP)
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs_value

    sleeve_rows = fetch_strategy_sleeves_for_account_fn(conn, account_id=account_id)
    total_equity = sum(float(row["current_equity"]) for row in sleeve_rows)
    max_symbol_concentration_pct = 0.0
    max_sector_concentration_pct = 0.0
    if total_equity > 0 and symbol_exposure:
        max_symbol_concentration_pct = max(symbol_exposure.values()) / total_equity
    if total_equity > 0 and sector_exposure:
        max_sector_concentration_pct = max(sector_exposure.values()) / total_equity
    return gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct


def persist_sleeve_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
    fetch_sleeve_positions_for_account_fn: Callable[..., list[Any]],
    fetch_strategy_sleeves_for_account_fn: Callable[..., list[Any]],
    upsert_portfolio_risk_snapshot_fn: Callable[..., object],
) -> None:
    gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct = (
        compute_current_exposure_snapshot(
            conn,
            account_id=account_id,
            fetch_sleeve_positions_for_account_fn=fetch_sleeve_positions_for_account_fn,
            fetch_strategy_sleeves_for_account_fn=fetch_strategy_sleeves_for_account_fn,
        )
    )
    upsert_portfolio_risk_snapshot_fn(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        max_symbol_concentration_pct=max_symbol_concentration_pct,
        max_sector_concentration_pct=max_sector_concentration_pct,
        drawdown_pct=None,
        leverage_proxy=None,
        daily_loss_pct=None,
        kill_switch_triggered=1 if kill_switch_triggered else 0,
        risk_payload_json=json.dumps(payload, sort_keys=True),
    )


def persist_normalized_sleeve_risk_decisions(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    decision_time: str,
    risk_decisions: list[dict[str, Any]],
    insert_sleeve_risk_decision_fn: Callable[..., object],
) -> None:
    for decision in risk_decisions:
        action = str(decision.get("action", "block")).strip().lower()
        reason_code = str(decision.get("reason_code", "unspecified")).strip().lower()
        sleeve_id_value = decision.get("sleeve_id")
        sleeve_id = int(sleeve_id_value) if sleeve_id_value is not None else None
        symbol_value = decision.get("symbol")
        symbol = str(symbol_value).upper().strip() if symbol_value is not None else None
        side_value = decision.get("side")
        side = str(side_value).lower().strip() if side_value is not None else None
        requested_qty_value = decision.get("requested_qty")
        approved_qty_value = decision.get("approved_qty")
        requested_notional_value = decision.get("requested_notional")
        approved_notional_value = decision.get("approved_notional")
        insert_sleeve_risk_decision_fn(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            decision_time=decision_time,
            symbol=symbol,
            side=side,
            action=action,
            reason_code=reason_code,
            requested_qty=int(requested_qty_value) if requested_qty_value is not None else None,
            approved_qty=int(approved_qty_value) if approved_qty_value is not None else None,
            requested_notional=(
                float(requested_notional_value) if requested_notional_value is not None else None
            ),
            approved_notional=(
                float(approved_notional_value) if approved_notional_value is not None else None
            ),
            execution_mode="sleeve",
            risk_payload_json=json.dumps(decision, sort_keys=True),
            created_at=decision_time,
        )


def is_snapshot_time_stale(
    *,
    snapshot_time: str | None,
    now_iso: str,
    max_age_seconds: int,
) -> bool:
    if snapshot_time is None:
        return True
    try:
        snapshot_dt = parse_utc_iso(snapshot_time)
        now_dt = parse_utc_iso(now_iso)
    except Exception:
        return True
    age_seconds = (now_dt - snapshot_dt).total_seconds()
    return age_seconds > float(max_age_seconds)
