"""Backend service helpers for account data in the paper-trading UI.

Responsibilities
----------------
- **Account summaries** — ``build_account_summary`` assembles the full 21-field
  account payload (equity, PnL, risk params, goal params, options params, etc.)
  from a DB row, current pricing state, and the latest snapshot.
- **Account parameter updates** — ``update_account_params`` accepts up to 23
  mutable config fields and delegates to ``configure_account`` (for all fields
  except ``strategy``, which is updated directly via ``update_account_fields_by_id``).
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

from trading.models.account_config import AccountConfig
from trading.utils.coercion import row_float, row_int
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
from trading.services.reporting_service import get_account_stats as build_account_stats

from ..config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_STRATEGY, TEST_BACKTEST_ACCOUNT_NAME
from .db import fetch_latest_snapshot_row

# CASH is the settlement fund ticker (always $1/share). It should not
# appear as a regular equity position — its value is shown as settlement cash.
_SETTLEMENT_TICKER = "CASH"
_SETTLEMENT_PRICE = 1.0


def build_account_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    from trading.models.account_state import AccountState
    state, prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    _inject_settlement_price(state, prices)
    if isinstance(state, AccountState) and isinstance(prices, dict):
        equity = state.cash + sum(
            state.positions.get(t, 0.0) * prices.get(t, 0.0) for t in state.positions
        )
    return _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices))


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
    summary = _build_summary_from_stats(conn, row, equity, _settlement_cash(state, prices))
    positions = _build_positions_from_stats(state, prices)
    return summary, positions


def _inject_settlement_price(state: object, prices: object) -> None:
    """Ensure CASH is priced at $1 even if yfinance doesn't return it."""
    from trading.models.account_state import AccountState
    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return
    if _SETTLEMENT_TICKER in state.positions and _SETTLEMENT_TICKER not in prices:
        prices[_SETTLEMENT_TICKER] = _SETTLEMENT_PRICE


def _settlement_cash(state: object, prices: object) -> float:
    from trading.models.account_state import AccountState
    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return 0.0
    qty = state.positions.get(_SETTLEMENT_TICKER, 0.0)
    return qty * prices.get(_SETTLEMENT_TICKER, _SETTLEMENT_PRICE)


def _build_summary_from_stats(
    conn: sqlite3.Connection, row: sqlite3.Row, equity: float, settlement_cash: float = 0.0
) -> dict[str, object]:
    latest_snapshot = fetch_latest_snapshot_row(conn, int(row["id"]))

    initial_cash = float(row["initial_cash"])
    delta = equity - initial_cash
    delta_pct = ((equity / initial_cash) - 1.0) * 100.0 if initial_cash else 0.0

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
        market_price = prices.get(ticker, 0.0)
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

