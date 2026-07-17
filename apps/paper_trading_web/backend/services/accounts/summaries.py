from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from trading.models import AccountRecord, AccountState
from trading.services.market_data import MarketDataProvider
from trading.services.accounts import (
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
    get_latest_account_snapshot,
)
from trading.services.books.book_assignments import active_strategy_for_account, get_default_book
from trading.services.books.rotation import resolve_default_book_rotation_schedule
from trading.services.reporting import (
    build_account_stats,
    inject_settlement_price,
    settlement_cash,
    settlement_corrected_equity,
)


def build_account_summary(
    conn: sqlite3.Connection,
    row: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, object]:
    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row, provider=provider)
    inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = settlement_corrected_equity(state, prices)
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    return _build_summary_from_stats(conn, row, equity, settlement_cash(state, prices), total_deposited)


def build_account_list_payload(summary: dict[str, object]) -> dict[str, object]:
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
        "accountKind": summary["accountKind"],
        "strategy": summary["strategy"],
        "instrumentMode": summary["instrumentMode"],
        "benchmark": summary["benchmark"],
        "equity": summary["equity"],
        "totalChange": summary["totalChange"],
        "totalChangePct": summary["totalChangePct"],
        "changeSinceLastSnapshot": summary["changeSinceLastSnapshot"],
        "latestSnapshotTime": summary["latestSnapshotTime"],
    }


def build_account_summary_and_positions(
    conn: sqlite3.Connection,
    row: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Call build_account_stats once and return both summary and open positions."""
    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row, provider=provider)
    inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = settlement_corrected_equity(state, prices)
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    summary = _build_summary_from_stats(conn, row, equity, settlement_cash(state, prices), total_deposited)
    positions = _build_positions_from_stats(state, prices)
    return summary, positions


def _build_summary_from_stats(
    conn: sqlite3.Connection,
    row: AccountRecord,
    equity: float,
    settlement_cash: float = 0.0,
    total_deposited: float = 0.0,
) -> dict[str, object]:
    latest_snapshot = get_latest_account_snapshot(conn, row.id)
    # Rotation scheduling is book-owned (ADR 014) and execution settings are
    # book columns (revision 0004): both read from the default book, alongside
    # the assignment-derived active strategy.
    rotation = resolve_default_book_rotation_schedule(conn, account_id=row.id)
    active_strategy = active_strategy_for_account(conn, row.id)
    book = get_default_book(conn, account_id=row.id)

    effective_initial = row.initial_cash if row.initial_cash else total_deposited
    delta = equity - effective_initial
    delta_pct = ((equity / effective_initial) - 1.0) * 100.0 if effective_initial else 0.0

    change_since_snapshot = None
    if latest_snapshot is not None:
        previous_equity = latest_snapshot.equity
        change_since_snapshot = equity - previous_equity

    return {
        "name": row.name,
        "displayName": row.descriptive_name,
        "strategy": active_strategy,
        "instrumentMode": book.instrument_mode if book is not None else "equity",
        "accountKind": row.account_kind,
        "brokerType": row.broker_type or "paper",
        "riskPolicy": book.risk_policy if book is not None else "none",
        "benchmark": row.benchmark_ticker,
        "initialCash": row.initial_cash,
        "equity": equity,
        "settlementCash": settlement_cash,
        "totalChange": delta,
        "totalChangePct": delta_pct,
        "changeSinceLastSnapshot": change_since_snapshot,
        "latestSnapshotTime": latest_snapshot.snapshot_time if latest_snapshot else None,
        "stopLossPct": book.stop_loss_pct if book is not None else None,
        "takeProfitPct": book.take_profit_pct if book is not None else None,
        "tradeSizePct": (
            book.trade_size_pct if book is not None and book.trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
        ),
        "maxPositionPct": (
            book.max_position_pct
            if book is not None and book.max_position_pct is not None
            else DEFAULT_MAX_POSITION_PCT
        ),
        "goalMinReturnPct": book.goal_min_return_pct if book is not None else None,
        "goalMaxReturnPct": book.goal_max_return_pct if book is not None else None,
        "goalPeriod": book.goal_period if book is not None else None,
        "learningEnabled": bool(book.learning_enabled) if book is not None else False,
        "optionStrikeOffsetPct": book.option_strike_offset_pct if book is not None else None,
        "optionMinDte": book.option_min_dte if book is not None else None,
        "optionMaxDte": book.option_max_dte if book is not None else None,
        "optionType": book.option_type if book is not None else None,
        "targetDeltaMin": book.target_delta_min if book is not None else None,
        "targetDeltaMax": book.target_delta_max if book is not None else None,
        "maxPremiumPerTrade": book.max_premium_per_trade if book is not None else None,
        "maxContractsPerTrade": book.max_contracts_per_trade if book is not None else None,
        "ivRankMin": book.iv_rank_min if book is not None else None,
        "ivRankMax": book.iv_rank_max if book is not None else None,
        "rollDteThreshold": book.roll_dte_threshold if book is not None else None,
        "profitTakePct": book.profit_take_pct if book is not None else None,
        "maxLossPct": book.max_loss_pct if book is not None else None,
        "activeStrategy": active_strategy,
        "rotation": {
            "enabled": rotation.rotation_enabled,
            "schedule": list(rotation.schedule) or None,
            "lookbackDays": rotation.lookback_days,
        },
    }


def _build_positions_from_stats(state: object, prices: dict[str, float]) -> list[dict[str, object]]:
    from trading.models.accounts.account_state import AccountState

    if not isinstance(state, AccountState):
        return []
    result = []
    for ticker, qty in sorted(state.positions.items()):
        if qty <= 0 or ticker == _SETTLEMENT_TICKER:
            continue
        avg_cost = state.avg_cost.get(ticker, 0.0)
        market_price = prices.get(ticker)
        if market_price is None:
            continue
        market_value = qty * market_price
        unrealized_pnl = (market_price - avg_cost) * qty
        result.append(
            {
                "ticker": ticker,
                "qty": qty,
                "avgCost": avg_cost,
                "marketPrice": market_price,
                "marketValue": market_value,
                "unrealizedPnl": unrealized_pnl,
            }
        )
    return result


def build_comparison_account_payload(
    summary: dict[str, object],
    latest_backtest: dict[str, object] | None,
    evaluation: dict[str, object],
) -> dict[str, object]:
    """Build comparison payload from a fully-enriched account summary.

    Precondition: ``summary`` must have been produced by calling
    ``attach_live_benchmark_summary`` after ``build_account_summary``;
    bare ``build_account_summary`` results lack the five live-benchmark keys
    and will raise ``KeyError`` here.
    """
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
        "strategy": summary["strategy"],
        "benchmark": summary["benchmark"],
        "equity": summary["equity"],
        "initialCash": summary["initialCash"],
        "totalChange": summary["totalChange"],
        "totalChangePct": summary["totalChangePct"],
        "liveBenchmarkReturnPct": summary["liveBenchmarkReturnPct"],
        "liveAlphaPct": summary["liveAlphaPct"],
        "latestBacktest": latest_backtest,
        "evaluation": evaluation,
    }
