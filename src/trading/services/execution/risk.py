"""Book-keyed risk persistence for runtime auto-trading (multi-book mode).

Exposure is derived from already-fetched rows, so the arithmetic behind
``risk_snapshots`` — concentration, leverage, drawdown — is testable without a
database, while the persistence around it reads and writes through the
repositories directly, as every other module in this package does.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from common.json_columns import dumps_json_column
from trading.domain.risk_gate import point_in_time_drawdown_pct, resolve_sector_for_symbol
from trading.models.books import RiskDecisionInsert, RiskSnapshotInsert
from trading.models.execution import BookRunAudit
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.books.sector_config import load_symbol_sector_map


def compute_current_exposure_snapshot(
    *,
    position_rows: Sequence[Any],
    book_rows: Sequence[Any],
    symbol_sector_map: dict[str, str],
) -> tuple[float, float, float, float, float]:
    """Gross, net, symbol/sector concentration and total equity over the given rows."""
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


def build_risk_snapshot(
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
    position_rows: Sequence[Any],
    book_rows: Sequence[Any],
    peak_equity: float | None,
    symbol_sector_map: dict[str, str],
) -> RiskSnapshotInsert:
    """Derive the account's risk snapshot row from already-fetched rows."""
    gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct, total_equity = (
        compute_current_exposure_snapshot(
            position_rows=position_rows,
            book_rows=book_rows,
            symbol_sector_map=symbol_sector_map,
        )
    )
    return RiskSnapshotInsert(
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
        risk_payload_json=dumps_json_column(payload),
    )


def persist_normalized_risk_decisions(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    decision_time: str,
    risk_decisions: list[dict[str, Any]],
) -> None:
    repository = RiskDecisionRepository(conn)
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
        repository.insert(
            RiskDecisionInsert(
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
                risk_payload_json=dumps_json_column(decision),
                created_at=decision_time,
            )
        )


def persist_book_run_audit(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    audit: BookRunAudit,
) -> None:
    """Persist one book run's risk audit: normalized decisions, then the snapshot.

    Exposure is sourced from the clean book positions/equity — the submission
    path's source of truth — and persisted to the account-keyed risk_snapshots
    table.
    """
    persist_normalized_risk_decisions(
        conn,
        account_id=account_id,
        decision_time=snapshot_time,
        risk_decisions=audit.risk_decisions,
    )
    RiskSnapshotRepository(conn).insert(
        build_risk_snapshot(
            account_id=account_id,
            snapshot_time=snapshot_time,
            kill_switch_triggered=bool(audit.kill_switch_reasons),
            payload={
                "kill_switch_reasons": audit.kill_switch_reasons,
                "risk_decisions": audit.risk_decisions,
                "summary": audit.summary(),
            },
            position_rows=PositionRepository(conn).fetch_for_account(account_id=account_id),
            book_rows=BookRepository(conn).fetch_for_account(account_id=account_id),
            peak_equity=EquitySnapshotRepository(conn).fetch_max_equity(account_id=account_id),
            symbol_sector_map=load_symbol_sector_map(),
        )
    )
