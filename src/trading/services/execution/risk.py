"""Book-keyed risk persistence helpers for runtime auto-trading (multi-book mode)."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from typing import Any

from trading.domain.risk_gate import point_in_time_drawdown_pct, resolve_sector_for_symbol

logger = logging.getLogger(__name__)


def compute_current_exposure_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    fetch_positions_for_account_fn: Callable[..., list[Any]],
    fetch_books_for_account_fn: Callable[..., list[Any]],
    symbol_sector_map: dict[str, str],
) -> tuple[float, float, float, float, float]:
    position_rows = fetch_positions_for_account_fn(conn, account_id=account_id)
    gross_exposure = 0.0
    net_exposure = 0.0
    symbol_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    for pos in position_rows:
        symbol = str(pos.symbol).upper().strip()
        market_value = float(pos.market_value)
        abs_value = abs(market_value)
        gross_exposure += abs_value
        net_exposure += market_value
        symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + abs_value
        sector = resolve_sector_for_symbol(symbol, symbol_sector_map=symbol_sector_map)
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs_value

    book_rows = fetch_books_for_account_fn(conn, account_id=account_id)
    total_equity = sum(float(b.current_equity) for b in book_rows)
    max_symbol_concentration_pct = 0.0
    max_sector_concentration_pct = 0.0
    if total_equity > 0 and symbol_exposure:
        max_symbol_concentration_pct = max(symbol_exposure.values()) / total_equity
    if total_equity > 0 and sector_exposure:
        max_sector_concentration_pct = max(sector_exposure.values()) / total_equity
    return gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct, total_equity


def _compute_leverage_proxy(*, gross_exposure: float, total_equity: float) -> float | None:
    return gross_exposure / total_equity if total_equity > 0 else None


def persist_book_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
    fetch_positions_for_account_fn: Callable[..., list[Any]],
    fetch_books_for_account_fn: Callable[..., list[Any]],
    fetch_max_equity_fn: Callable[..., float | None],
    insert_risk_snapshot_fn: Callable[..., object],
    symbol_sector_map: dict[str, str],
) -> None:
    gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct, total_equity = (
        compute_current_exposure_snapshot(
            conn,
            account_id=account_id,
            fetch_positions_for_account_fn=fetch_positions_for_account_fn,
            fetch_books_for_account_fn=fetch_books_for_account_fn,
            symbol_sector_map=symbol_sector_map,
        )
    )
    peak_equity = fetch_max_equity_fn(conn, account_id=account_id)
    insert_risk_snapshot_fn(
        account_id=account_id,
        snapshot_time=snapshot_time,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        max_symbol_concentration_pct=max_symbol_concentration_pct,
        max_sector_concentration_pct=max_sector_concentration_pct,
        drawdown_pct=point_in_time_drawdown_pct(total_equity=total_equity, peak_equity=peak_equity),
        leverage_proxy=_compute_leverage_proxy(gross_exposure=gross_exposure, total_equity=total_equity),
        # daily_loss_pct is a single-day peak-to-trough figure; still needs
        # intraday equity ticks this codebase does not persist (unlike
        # drawdown_pct above, a trailing-history peak can't stand in for it).
        daily_loss_pct=None,
        kill_switch_triggered=1 if kill_switch_triggered else 0,
        risk_payload_json=json.dumps(payload, sort_keys=True),
    )


def persist_normalized_risk_decisions(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    decision_time: str,
    risk_decisions: list[dict[str, Any]],
    insert_risk_decision_fn: Callable[..., object],
) -> None:
    for decision in risk_decisions:
        action = str(decision.get("action", "block")).strip().lower()
        reason_code = str(decision.get("reason_code", "unspecified")).strip().lower()
        book_id_value = decision.get("book_id")
        book_id = int(book_id_value) if book_id_value is not None else None
        symbol_value = decision.get("symbol")
        symbol = str(symbol_value).upper().strip() if symbol_value is not None else None
        side_value = decision.get("side")
        side = str(side_value).lower().strip() if side_value is not None else None
        requested_qty_value = decision.get("requested_qty")
        approved_qty_value = decision.get("approved_qty")
        requested_notional_value = decision.get("requested_notional")
        approved_notional_value = decision.get("approved_notional")
        insert_risk_decision_fn(
            conn,
            account_id=account_id,
            book_id=book_id,
            decision_time=decision_time,
            symbol=symbol,
            side=side,
            action=action,
            reason_code=reason_code,
            requested_qty=float(requested_qty_value) if requested_qty_value is not None else None,
            approved_qty=float(approved_qty_value) if approved_qty_value is not None else None,
            requested_notional=(float(requested_notional_value) if requested_notional_value is not None else None),
            approved_notional=(float(approved_notional_value) if approved_notional_value is not None else None),
            risk_payload_json=json.dumps(decision, sort_keys=True),
            created_at=decision_time,
        )
