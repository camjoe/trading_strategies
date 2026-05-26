from __future__ import annotations

import json
from dataclasses import dataclass
import random
import sqlite3

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_int
import trading.domain.auto_trading_policy as auto_trader_policy
from trading.domain.rotation import resolve_active_strategy
from trading.models import AccountRecord
from trading.repositories.sleeve_positions import fetch_sleeve_positions
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_strategy_sleeves_for_account,
)
from trading.services.universe.resolver import resolve_named_universes


@dataclass(frozen=True, slots=True)
class SleeveTradeState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float = 0.0


@dataclass(frozen=True, slots=True)
class SleeveTradeIntent:
    account_id: int
    sleeve_id: int
    strategy_name: str
    param_set_id: int | None
    side: str
    symbol: str
    qty: int
    requested_price: float
    forced_sell: str | None
    delta_est: float | None
    iv_est: float | None


def _prepare_trade_selection(*args, **kwargs):
    from trading.services.auto_trading.execution import prepare_trade_selection

    return prepare_trade_selection(*args, **kwargs)


def _build_sleeve_state(conn: sqlite3.Connection, *, sleeve_id: int, current_cash: float) -> SleeveTradeState:
    position_rows = fetch_sleeve_positions(conn, sleeve_id=sleeve_id)
    positions: dict[str, float] = {}
    avg_cost: dict[str, float] = {}
    for row in position_rows:
        symbol = row_expect_str(row, "symbol")
        qty = row_expect_float(row, "qty")
        if qty <= 0:
            continue
        positions[symbol] = qty
        avg_cost[symbol] = row_expect_float(row, "avg_cost")
    return SleeveTradeState(
        cash=float(current_cash),
        positions=positions,
        avg_cost=avg_cost,
    )


def generate_sleeve_trade_intents(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> list[SleeveTradeIntent]:
    account_id = row_expect_int(account, "id")
    learning_enabled = bool(int(account["learning_enabled"] or 0))
    risk_policy = str(account["risk_policy"]).strip().lower()
    stop_loss_pct = account["stop_loss_pct"]
    take_profit_pct = account["take_profit_pct"]
    instrument_mode = str(account["instrument_mode"]).strip().lower()
    default_strategy = resolve_active_strategy(account) or row_expect_str(account, "strategy")

    sleeve_rows = [
        row
        for row in fetch_strategy_sleeves_for_account(conn, account_id=account_id)
        if str(row["status"]).strip().lower() == "active"
    ]
    if not sleeve_rows:
        return []

    target = random.randint(min_trades, max_trades)
    max_intents = min(target, len(sleeve_rows))
    intents: list[SleeveTradeIntent] = []
    for sleeve_row in sleeve_rows:
        if len(intents) >= max_intents:
            break
        sleeve_id = row_expect_int(sleeve_row, "id")
        raw_sleeve_universes = sleeve_row["trade_universes"] if "trade_universes" in sleeve_row.keys() else None
        if raw_sleeve_universes:
            sleeve_names: object = json.loads(str(raw_sleeve_universes))
            if isinstance(sleeve_names, list) and sleeve_names:
                effective_universe = resolve_named_universes([str(n) for n in sleeve_names])
            else:
                effective_universe = universe
        else:
            effective_universe = universe
        state = _build_sleeve_state(
            conn,
            sleeve_id=sleeve_id,
            current_cash=row_expect_float(sleeve_row, "current_cash"),
        )
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sell = auto_trader_policy.choose_sell_ticker_by_risk(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )
        assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        strategy_name = (
            row_expect_str(assignment, "strategy_name")
            if assignment is not None and assignment["strategy_name"] is not None
            else default_strategy
        )
        param_set_id = row_int(assignment, "param_set_id") if assignment is not None else None
        selection = _prepare_trade_selection(
            account,
            strategy_name,
            state,
            can_sell,
            forced_sell,
            effective_universe,
            prices,
            iv_rank_proxy,
            learning_enabled,
            instrument_mode,
            fee,
        )
        if selection is None:
            continue
        side, symbol, qty, requested_price, delta_est, iv_est = selection
        intents.append(
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name=strategy_name,
                param_set_id=param_set_id,
                side=side,
                symbol=symbol,
                qty=qty,
                requested_price=requested_price,
                forced_sell=forced_sell,
                delta_est=delta_est,
                iv_est=iv_est,
            )
        )
    return intents


def run_sleeve_mode_for_account(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> int:
    return len(
        generate_sleeve_trade_intents(
            conn,
            account=account,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            min_trades=min_trades,
            max_trades=max_trades,
            fee=fee,
        )
    )
