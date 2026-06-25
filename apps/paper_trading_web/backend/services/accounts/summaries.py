from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from trading.models import AccountRecord, AccountState
from trading.services.market_data import MarketDataProvider
from trading.services.accounts import (
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
    get_latest_account_snapshot,
    parse_rotation_overlay_watchlist,
    parse_rotation_schedule,
)
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
    rotation_schedule = parse_rotation_schedule(row.rotation_schedule)
    rotation_overlay_watchlist = parse_rotation_overlay_watchlist(row.rotation_overlay_watchlist)

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
        "strategy": row.strategy,
        "instrumentMode": row.instrument_mode,
        "accountKind": row.account_kind,
        "brokerType": row.broker_type or "paper",
        "riskPolicy": row.risk_policy,
        "benchmark": row.benchmark_ticker,
        "initialCash": row.initial_cash,
        "equity": equity,
        "settlementCash": settlement_cash,
        "totalChange": delta,
        "totalChangePct": delta_pct,
        "changeSinceLastSnapshot": change_since_snapshot,
        "latestSnapshotTime": latest_snapshot.snapshot_time if latest_snapshot else None,
        "stopLossPct": row.stop_loss_pct,
        "takeProfitPct": row.take_profit_pct,
        "tradeSizePct": (row.trade_size_pct if row.trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT),
        "maxPositionPct": (row.max_position_pct if row.max_position_pct is not None else DEFAULT_MAX_POSITION_PCT),
        "goalMinReturnPct": row.goal_min_return_pct,
        "goalMaxReturnPct": row.goal_max_return_pct,
        "goalPeriod": row.goal_period,
        "learningEnabled": bool(row.learning_enabled),
        "optionStrikeOffsetPct": row.option_strike_offset_pct,
        "optionMinDte": row.option_min_dte,
        "optionMaxDte": row.option_max_dte,
        "optionType": row.option_type,
        "targetDeltaMin": row.target_delta_min,
        "targetDeltaMax": row.target_delta_max,
        "maxPremiumPerTrade": row.max_premium_per_trade,
        "maxContractsPerTrade": row.max_contracts_per_trade,
        "ivRankMin": row.iv_rank_min,
        "ivRankMax": row.iv_rank_max,
        "rollDteThreshold": row.roll_dte_threshold,
        "profitTakePct": row.profit_take_pct,
        "maxLossPct": row.max_loss_pct,
        "rotationEnabled": bool(row.rotation_enabled),
        "rotationMode": row.rotation_mode or "time",
        "rotationOptimalityMode": row.rotation_optimality_mode or "previous_period_best",
        "rotationIntervalDays": row.rotation_interval_days,
        "rotationIntervalMinutes": row.rotation_interval_minutes,
        "rotationLookbackDays": row.rotation_lookback_days,
        "rotationSchedule": rotation_schedule or None,
        "rotationRegimeStrategyRiskOn": row.rotation_regime_strategy_risk_on,
        "rotationRegimeStrategyNeutral": row.rotation_regime_strategy_neutral,
        "rotationRegimeStrategyRiskOff": row.rotation_regime_strategy_risk_off,
        "rotationOverlayMode": row.rotation_overlay_mode or "none",
        "rotationOverlayMinTickers": row.rotation_overlay_min_tickers,
        "rotationOverlayConfidenceThreshold": row.rotation_overlay_confidence_threshold,
        "rotationOverlayWatchlist": rotation_overlay_watchlist,
        "rotationActiveIndex": row.rotation_active_index if row.rotation_active_index is not None else 0,
        "rotationLastAt": row.rotation_last_at,
        "rotationActiveStrategy": row.rotation_active_strategy,
    }


def _build_positions_from_stats(state: object, prices: dict[str, float]) -> list[dict[str, object]]:
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
