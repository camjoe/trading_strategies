"""Backend service helpers for account data in the paper-trading UI.

Responsibilities
----------------
- **Account summaries** — ``build_account_summary`` assembles the account
  payload (equity, PnL, risk params, goal params, options params, rotation
  params, etc.)
  from a DB row, current pricing state, and the latest snapshot.
- **Account parameter updates** — ``update_account_params`` accepts mutable
  config fields plus rotation settings and delegates to canonical trading
  services.
- **Backtest helpers** — functions to fetch and format the latest backtest run
  summary and performance metrics for an account.
- **Listing and filtering** — managed-account row listing, account-name lookup,
  snapshot history, and recent backtest run summaries.
- **Snapshot / trade helpers** — ``take_snapshot``, ``fetch_account_trades``,
  and payload-shaping functions for snapshots and trade records.
- **Display-name normalisation** — ``display_account_name`` / ``display_strategy``
  map the internal ``test_backtest_account`` name back to the ``test_account``
  display label in backtest summaries.

All DB access is performed through canonical ``trading.*`` service and repository
adapters — no inline SQL lives here.
"""
from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from common.coercion import coerce_float, coerce_int, row_float, row_int
from trading.domain.rotation import (
    parse_rotation_overlay_watchlist,
    parse_rotation_schedule,
)
from trading.models.account_config import AccountConfig
from trading.backtesting.services.report_service import (
    fetch_backtest_report_summary,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs,
)
from trading.services.accounts_service import (
    fetch_account_rows_excluding,
    fetch_all_account_names,
    fetch_snapshot_history_rows,
    update_account_fields_by_id,
)
from trading.services.profiles_service import apply_rotation_fields
from trading.services.reporting_service import get_account_stats as build_account_stats

from ..config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_STRATEGY, TEST_BACKTEST_ACCOUNT_NAME
from .db import fetch_latest_snapshot_row

_SETTLEMENT_PRICE = 1.0


def _row_value(row: sqlite3.Row | dict[str, object], key: str) -> object | None:
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return None


def build_account_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    from trading.models.account_state import AccountState
    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    _inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = state.cash + sum(
            state.positions.get(t, 0.0) * prices.get(t, 0.0) for t in state.positions
        )
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    return _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices), total_deposited)


def build_account_summary_and_positions(
    conn: sqlite3.Connection, row: sqlite3.Row
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Call build_account_stats once and return both summary and open positions.

    Use this in endpoints where both are needed to avoid double price fetches.
    CASH (settlement fund) is excluded from the positions list
    and surfaced as ``settlementCash`` in the summary dict.
    """
    from trading.models.account_state import AccountState
    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    _inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = state.cash + sum(
            state.positions.get(t, 0.0) * prices.get(t, 0.0) for t in state.positions
        )
    total_deposited = state.total_deposited if isinstance(state, AccountState) else 0.0
    summary = _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices), total_deposited)
    positions = _build_positions_from_stats(state, prices)
    return summary, positions


def _inject_settlement_price(state: object, prices: object) -> None:
    """Ensure CASH is priced at $1 even if yfinance doesn't return it.

    Under the deposit model CASH never enters positions, so this is a no-op
    for accounts using that model. Kept for safety in case any legacy row still
    carries a CASH position.
    """
    from trading.models.account_state import AccountState
    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return
    if _SETTLEMENT_TICKER in state.positions and _SETTLEMENT_TICKER not in prices:
        prices[_SETTLEMENT_TICKER] = _SETTLEMENT_PRICE


def _settlement_cash(state: object, prices: object) -> float:
    """Return the free cash balance for use as the ``settlementCash`` API field.

    Under the deposit model, CASH buy trades are treated as inflows into
    ``state.cash`` directly (no position created), so ``state.cash`` represents
    all uninvested cash for every account type. This replaces the old behaviour
    of reading the CASH position qty — which returned 0.0 for non-deposit
    accounts and double-counted for the test account.
    """
    from trading.models.account_state import AccountState
    if not isinstance(state, AccountState):
        return 0.0
    # After the deposit model: CASH buys are inflows that go into state.cash directly.
    # state.positions no longer contains the settlement ticker.
    return state.cash


def _build_summary_from_stats(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    equity: float,
    settlement_cash: float = 0.0,
    total_deposited: float = 0.0,
) -> dict[str, object]:
    latest_snapshot = fetch_latest_snapshot_row(conn, int(row["id"]))
    rotation_schedule = parse_rotation_schedule(_row_value(row, "rotation_schedule"))
    rotation_overlay_watchlist = parse_rotation_overlay_watchlist(
        _row_value(row, "rotation_overlay_watchlist")
    )
    rotation_active_index = coerce_int(_row_value(row, "rotation_active_index"))

    initial_cash = float(row["initial_cash"])
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
        "goalMinReturnPct": row_float(row, "goal_min_return_pct"),
        "goalMaxReturnPct": row_float(row, "goal_max_return_pct"),
        "goalPeriod": row["goal_period"] if "goal_period" in row.keys() else None,
        "learningEnabled": bool(row["learning_enabled"]) if row["learning_enabled"] is not None else False,
        "optionStrikeOffsetPct": row_float(row, "option_strike_offset_pct"),
        "optionMinDte": row_int(row, "option_min_dte"),
        "optionMaxDte": row_int(row, "option_max_dte"),
        "optionType": row["option_type"] if "option_type" in row.keys() else None,
        "targetDeltaMin": row_float(row, "target_delta_min"),
        "targetDeltaMax": row_float(row, "target_delta_max"),
        "maxPremiumPerTrade": row_float(row, "max_premium_per_trade"),
        "maxContractsPerTrade": row_int(row, "max_contracts_per_trade"),
        "ivRankMin": row_float(row, "iv_rank_min"),
        "ivRankMax": row_float(row, "iv_rank_max"),
        "rollDteThreshold": row_int(row, "roll_dte_threshold"),
        "profitTakePct": row_float(row, "profit_take_pct"),
        "maxLossPct": row_float(row, "max_loss_pct"),
        "rotationEnabled": bool(coerce_int(_row_value(row, "rotation_enabled")) or 0),
        "rotationMode": str(_row_value(row, "rotation_mode") or "time"),
        "rotationOptimalityMode": str(_row_value(row, "rotation_optimality_mode") or "previous_period_best"),
        "rotationIntervalDays": coerce_int(_row_value(row, "rotation_interval_days")),
        "rotationIntervalMinutes": coerce_int(_row_value(row, "rotation_interval_minutes")),
        "rotationLookbackDays": coerce_int(_row_value(row, "rotation_lookback_days")),
        "rotationSchedule": rotation_schedule or None,
        "rotationRegimeStrategyRiskOn": _row_value(row, "rotation_regime_strategy_risk_on"),
        "rotationRegimeStrategyNeutral": _row_value(row, "rotation_regime_strategy_neutral"),
        "rotationRegimeStrategyRiskOff": _row_value(row, "rotation_regime_strategy_risk_off"),
        "rotationOverlayMode": str(_row_value(row, "rotation_overlay_mode") or "none"),
        "rotationOverlayMinTickers": coerce_int(_row_value(row, "rotation_overlay_min_tickers")),
        "rotationOverlayConfidenceThreshold": coerce_float(_row_value(row, "rotation_overlay_confidence_threshold")),
        "rotationOverlayWatchlist": rotation_overlay_watchlist,
        "rotationActiveIndex": rotation_active_index if rotation_active_index is not None else 0,
        "rotationLastAt": _row_value(row, "rotation_last_at"),
        "rotationActiveStrategy": _row_value(row, "rotation_active_strategy"),
    }


def _build_positions_from_stats(
    state: object, prices: dict[str, float]
) -> list[dict[str, object]]:
    from trading.models.account_state import AccountState

    assert isinstance(state, AccountState)
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
        result.append({
            "ticker": ticker,
            "qty": qty,
            "avgCost": avg_cost,
            "marketPrice": market_price,
            "marketValue": market_value,
            "unrealizedPnl": unrealized_pnl,
        })
    return result


def fetch_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    row = fetch_latest_backtest_run_for_account(conn, account_name=account_name)
    if row is None:
        return None
    return build_backtest_run_summary(row)


def build_backtest_run_summary(row: sqlite3.Row) -> dict[str, object]:
    account_name = str(row["account_name"])
    account_display_name = display_account_name(account_name)
    strategy_display_name = display_strategy(account_name, str(row["strategy"]))

    return {
        "runId": int(row["id"]),
        "runName": row["run_name"],
        "accountName": account_display_name,
        "strategy": strategy_display_name,
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": float(row["slippage_bps"]),
        "feePerTrade": float(row["fee_per_trade"]),
        "tickersFile": row["tickers_file"],
    }


def display_account_name(account_name: str) -> str:
    return TEST_ACCOUNT_NAME if account_name == TEST_BACKTEST_ACCOUNT_NAME else account_name


def display_strategy(account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if account_name == TEST_BACKTEST_ACCOUNT_NAME else strategy


def fetch_managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding(conn, excluded_name=TEST_BACKTEST_ACCOUNT_NAME)


def fetch_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names(conn)


def fetch_account_snapshot_rows(conn: sqlite3.Connection, account_id: int, *, limit: int = 100) -> list[sqlite3.Row]:
    return fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = fetch_recent_backtest_runs(conn, limit=limit)
    return [build_backtest_run_summary(row) for row in rows]


def build_comparison_account_payload(
    summary: dict[str, object],
    latest_backtest: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
        "strategy": summary["strategy"],
        "benchmark": summary["benchmark"],
        "equity": summary["equity"],
        "initialCash": summary["initialCash"],
        "totalChange": summary["totalChange"],
        "totalChangePct": summary["totalChangePct"],
        "latestBacktest": latest_backtest,
    }


def build_snapshot_payload(snapshot: sqlite3.Row) -> dict[str, object]:
    return {
        "time": snapshot["snapshot_time"],
        "cash": float(snapshot["cash"]),
        "marketValue": float(snapshot["market_value"]),
        "equity": float(snapshot["equity"]),
        "realizedPnl": float(snapshot["realized_pnl"]),
        "unrealizedPnl": float(snapshot["unrealized_pnl"]),
    }


def build_trade_payload(trade: sqlite3.Row) -> dict[str, object]:
    return {
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": float(trade["qty"]),
        "price": float(trade["price"]),
        "fee": float(trade["fee"]),
        "tradeTime": trade["trade_time"],
        "note": trade["note"],
    }


def fetch_latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    latest_run_id = fetch_latest_backtest_run_id_for_account(conn, account_name=account_name)
    if latest_run_id is None:
        return None

    report = fetch_backtest_report_summary(conn, int(latest_run_id))
    return {
        "runId": report.run_id,
        "endDate": report.end_date,
        "totalReturnPct": report.total_return_pct,
        "maxDrawdownPct": report.max_drawdown_pct,
        "alphaPct": None,
        "sharpeRatio": getattr(report, "sharpe_ratio", None),
        "sortinoRatio": getattr(report, "sortino_ratio", None),
        "calmarRatio": getattr(report, "calmar_ratio", None),
        "winRatePct": getattr(report, "win_rate_pct", None),
        "profitFactor": getattr(report, "profit_factor", None),
        "avgTradeReturnPct": getattr(report, "avg_trade_return_pct", None),
    }


def fetch_account_trades(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    from trading.services.reporting_service import load_account_trades
    return load_account_trades(conn, account_id)


def take_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    from trading.services.reporting_service import take_account_snapshot
    take_account_snapshot(conn, account_name, snapshot_time=snapshot_time)


def update_account_params(
    conn: sqlite3.Connection,
    account_id: int,
    account_name: str,
    *,
    strategy: str | None = None,
    risk_policy: str | None = None,
    descriptive_name: str | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    instrument_mode: str | None = None,
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str | None = None,
    learning_enabled: bool | None = None,
    option_strike_offset_pct: float | None = None,
    option_min_dte: int | None = None,
    option_max_dte: int | None = None,
    option_type: str | None = None,
    target_delta_min: float | None = None,
    target_delta_max: float | None = None,
    max_premium_per_trade: float | None = None,
    max_contracts_per_trade: int | None = None,
    iv_rank_min: float | None = None,
    iv_rank_max: float | None = None,
    roll_dte_threshold: int | None = None,
    profit_take_pct: float | None = None,
    max_loss_pct: float | None = None,
    rotation_enabled: bool | None = None,
    rotation_mode: str | None = None,
    rotation_optimality_mode: str | None = None,
    rotation_interval_days: int | None = None,
    rotation_interval_minutes: int | None = None,
    rotation_lookback_days: int | None = None,
    rotation_schedule: list[str] | None = None,
    rotation_regime_strategy_risk_on: str | None = None,
    rotation_regime_strategy_neutral: str | None = None,
    rotation_regime_strategy_risk_off: str | None = None,
    rotation_overlay_mode: str | None = None,
    rotation_overlay_min_tickers: int | None = None,
    rotation_overlay_confidence_threshold: float | None = None,
    rotation_overlay_watchlist: list[str] | None = None,
    rotation_active_index: int | None = None,
    rotation_last_at: str | None = None,
    rotation_active_strategy: str | None = None,
) -> None:
    """Update mutable account parameters. Only supplied (non-None) fields are changed."""
    # strategy is not handled by configure_account — update directly by id
    if strategy is not None:
        update_account_fields_by_id(conn, account_id, updates=["strategy = ?"], params=[strategy])

    cfg = AccountConfig(
        descriptive_name=descriptive_name,
        risk_policy=risk_policy,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        instrument_mode=instrument_mode,
        goal_min_return_pct=goal_min_return_pct,
        goal_max_return_pct=goal_max_return_pct,
        goal_period=goal_period,
        learning_enabled=learning_enabled,
        option_strike_offset_pct=option_strike_offset_pct,
        option_min_dte=option_min_dte,
        option_max_dte=option_max_dte,
        option_type=option_type,
        target_delta_min=target_delta_min,
        target_delta_max=target_delta_max,
        max_premium_per_trade=max_premium_per_trade,
        max_contracts_per_trade=max_contracts_per_trade,
        iv_rank_min=iv_rank_min,
        iv_rank_max=iv_rank_max,
        roll_dte_threshold=roll_dte_threshold,
        profit_take_pct=profit_take_pct,
        max_loss_pct=max_loss_pct,
    )
    from trading.services.accounts_service import configure_account
    configure_account(conn, account_name, cfg)

    rotation_profile: dict[str, object] = {}
    if rotation_enabled is not None:
        rotation_profile["rotation_enabled"] = rotation_enabled
    if rotation_mode is not None:
        rotation_profile["rotation_mode"] = rotation_mode
    if rotation_optimality_mode is not None:
        rotation_profile["rotation_optimality_mode"] = rotation_optimality_mode
    if rotation_interval_days is not None:
        rotation_profile["rotation_interval_days"] = rotation_interval_days
    if rotation_interval_minutes is not None:
        rotation_profile["rotation_interval_minutes"] = rotation_interval_minutes
    if rotation_lookback_days is not None:
        rotation_profile["rotation_lookback_days"] = rotation_lookback_days
    if rotation_schedule is not None:
        rotation_profile["rotation_schedule"] = rotation_schedule
    if rotation_regime_strategy_risk_on is not None:
        rotation_profile["rotation_regime_strategy_risk_on"] = rotation_regime_strategy_risk_on
    if rotation_regime_strategy_neutral is not None:
        rotation_profile["rotation_regime_strategy_neutral"] = rotation_regime_strategy_neutral
    if rotation_regime_strategy_risk_off is not None:
        rotation_profile["rotation_regime_strategy_risk_off"] = rotation_regime_strategy_risk_off
    if rotation_overlay_mode is not None:
        rotation_profile["rotation_overlay_mode"] = rotation_overlay_mode
    if rotation_overlay_min_tickers is not None:
        rotation_profile["rotation_overlay_min_tickers"] = rotation_overlay_min_tickers
    if rotation_overlay_confidence_threshold is not None:
        rotation_profile["rotation_overlay_confidence_threshold"] = rotation_overlay_confidence_threshold
    if rotation_overlay_watchlist is not None:
        rotation_profile["rotation_overlay_watchlist"] = rotation_overlay_watchlist
    if rotation_active_index is not None:
        rotation_profile["rotation_active_index"] = rotation_active_index
    if rotation_last_at is not None:
        rotation_profile["rotation_last_at"] = rotation_last_at
    if rotation_active_strategy is not None:
        rotation_profile["rotation_active_strategy"] = rotation_active_strategy

    if rotation_profile:
        apply_rotation_fields(conn, account_name, rotation_profile)
