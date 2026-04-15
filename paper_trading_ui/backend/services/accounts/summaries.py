from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from common.coercion import coerce_float, coerce_int, row_expect_int, row_float, row_int
from trading.services.accounts_service import (
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
    parse_rotation_overlay_watchlist,
    parse_rotation_schedule,
)
from trading.services.reporting_service import build_account_stats

from ..db import fetch_latest_snapshot_row

_SETTLEMENT_PRICE = 1.0


def _settlement_corrected_equity(state: object, prices: object) -> float:
    """Equity including the settlement position (cash-equivalent held as a ticker)."""
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return 0.0
    return state.cash + sum(
        state.positions.get(t, 0.0) * prices.get(t, 0.0) for t in state.positions
    )


def build_account_summary(conn: sqlite3.Connection, row: dict[str, object]) -> dict[str, object]:
    from trading.models.account_state import AccountState

    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    _inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = _settlement_corrected_equity(state, prices)
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    return _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices), total_deposited)


def build_account_list_payload(summary: dict[str, object]) -> dict[str, object]:
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
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
    conn: sqlite3.Connection, row: dict[str, object]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Call build_account_stats once and return both summary and open positions."""
    from trading.models.account_state import AccountState

    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    _inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = _settlement_corrected_equity(state, prices)
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    summary = _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices), total_deposited)
    positions = _build_positions_from_stats(state, prices)
    return summary, positions


def _inject_settlement_price(state: object, prices: object) -> None:
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return
    if _SETTLEMENT_TICKER in state.positions and _SETTLEMENT_TICKER not in prices:
        prices[_SETTLEMENT_TICKER] = _SETTLEMENT_PRICE


def _settlement_cash(state: object, prices: object) -> float:
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState):
        return 0.0
    return state.cash


def _build_summary_from_stats(
    conn: sqlite3.Connection,
    row: dict[str, object],
    equity: float,
    settlement_cash: float = 0.0,
    total_deposited: float = 0.0,
) -> dict[str, object]:
    latest_snapshot = fetch_latest_snapshot_row(conn, row_expect_int(row, "id"))  # type: ignore[arg-type]
    rotation_schedule = parse_rotation_schedule(row.get("rotation_schedule"))
    rotation_overlay_watchlist = parse_rotation_overlay_watchlist(
        row.get("rotation_overlay_watchlist")
    )
    rotation_active_index = coerce_int(row.get("rotation_active_index"))

    initial_cash = row_float(row, "initial_cash")
    effective_initial = initial_cash if initial_cash else total_deposited
    delta = equity - effective_initial
    delta_pct = ((equity / effective_initial) - 1.0) * 100.0 if effective_initial else 0.0

    change_since_snapshot = None
    if latest_snapshot is not None:
        previous_equity = float(latest_snapshot["equity"])
        change_since_snapshot = equity - previous_equity

    return {
        "name": row["name"],
        "displayName": row["descriptive_name"],
        "strategy": row["strategy"],
        "instrumentMode": row["instrument_mode"],
        "riskPolicy": row["risk_policy"],
        "benchmark": row["benchmark_ticker"],
        "initialCash": initial_cash,
        "equity": equity,
        "settlementCash": settlement_cash,
        "totalChange": delta,
        "totalChangePct": delta_pct,
        "changeSinceLastSnapshot": change_since_snapshot,
        "latestSnapshotTime": latest_snapshot["snapshot_time"] if latest_snapshot else None,
        "stopLossPct": row_float(row, "stop_loss_pct"),
        "takeProfitPct": row_float(row, "take_profit_pct"),
        "tradeSizePct": coerce_float(row.get("trade_size_pct")) if coerce_float(row.get("trade_size_pct")) is not None else DEFAULT_TRADE_SIZE_PCT,
        "maxPositionPct": coerce_float(row.get("max_position_pct")) if coerce_float(row.get("max_position_pct")) is not None else DEFAULT_MAX_POSITION_PCT,
        "goalMinReturnPct": row_float(row, "goal_min_return_pct"),
        "goalMaxReturnPct": row_float(row, "goal_max_return_pct"),
        "goalPeriod": row.get("goal_period"),
        "learningEnabled": bool(row["learning_enabled"]) if row["learning_enabled"] is not None else False,
        "optionStrikeOffsetPct": row_float(row, "option_strike_offset_pct"),
        "optionMinDte": row_int(row, "option_min_dte"),
        "optionMaxDte": row_int(row, "option_max_dte"),
        "optionType": row.get("option_type"),
        "targetDeltaMin": row_float(row, "target_delta_min"),
        "targetDeltaMax": row_float(row, "target_delta_max"),
        "maxPremiumPerTrade": row_float(row, "max_premium_per_trade"),
        "maxContractsPerTrade": row_int(row, "max_contracts_per_trade"),
        "ivRankMin": row_float(row, "iv_rank_min"),
        "ivRankMax": row_float(row, "iv_rank_max"),
        "rollDteThreshold": row_int(row, "roll_dte_threshold"),
        "profitTakePct": row_float(row, "profit_take_pct"),
        "maxLossPct": row_float(row, "max_loss_pct"),
        "rotationEnabled": bool(coerce_int(row.get("rotation_enabled")) or 0),
        "rotationMode": str(row.get("rotation_mode") or "time"),
        "rotationOptimalityMode": str(row.get("rotation_optimality_mode") or "previous_period_best"),
        "rotationIntervalDays": coerce_int(row.get("rotation_interval_days")),
        "rotationIntervalMinutes": coerce_int(row.get("rotation_interval_minutes")),
        "rotationLookbackDays": coerce_int(row.get("rotation_lookback_days")),
        "rotationSchedule": rotation_schedule or None,
        "rotationRegimeStrategyRiskOn": row.get("rotation_regime_strategy_risk_on"),
        "rotationRegimeStrategyNeutral": row.get("rotation_regime_strategy_neutral"),
        "rotationRegimeStrategyRiskOff": row.get("rotation_regime_strategy_risk_off"),
        "rotationOverlayMode": str(row.get("rotation_overlay_mode") or "none"),
        "rotationOverlayMinTickers": coerce_int(row.get("rotation_overlay_min_tickers")),
        "rotationOverlayConfidenceThreshold": coerce_float(row.get("rotation_overlay_confidence_threshold")),
        "rotationOverlayWatchlist": rotation_overlay_watchlist,
        "rotationActiveIndex": rotation_active_index if rotation_active_index is not None else 0,
        "rotationLastAt": row.get("rotation_last_at"),
        "rotationActiveStrategy": row.get("rotation_active_strategy"),
    }


def _build_positions_from_stats(
    state: object, prices: dict[str, float]
) -> list[dict[str, object]]:
    from trading.models.account_state import AccountState

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
    }
