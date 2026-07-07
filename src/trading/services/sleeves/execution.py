from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Mapping

import pandas as pd

import trading.domain.auto_trading_policy as auto_trader_policy
from trading.models import AccountRecord
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.models.sleeves.sleeve_trade_state import SleeveTradeState
from trading.repositories.book_bridge import book_id_for_sleeve
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.services.universe import resolve_named_universes

if TYPE_CHECKING:
    from trading.services.auto_trading.execution import FeatureHistoryFn


def _prepare_trade_selection(*args, **kwargs):
    from trading.services.auto_trading.execution import prepare_trade_selection

    return prepare_trade_selection(*args, **kwargs)


def _build_sleeve_state(conn: sqlite3.Connection, *, book_id: int) -> SleeveTradeState:
    # A sleeve's live state (cash + holdings) is its bridging book's — the submission
    # path maintains book balances/positions, and the sleeve_positions/strategy_sleeves
    # tables are frozen once sleeve mode submits through the shared execution service.
    book = BookRepository(conn).fetch_by_id(book_id=book_id)
    current_cash = book.current_cash if book is not None else 0.0
    positions: dict[str, float] = {}
    avg_cost: dict[str, float] = {}
    for pos in PositionRepository(conn).fetch_for_book(book_id=book_id):
        if pos.qty <= 0:
            continue
        positions[pos.symbol] = pos.qty
        avg_cost[pos.symbol] = pos.avg_cost
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
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> list[SleeveTradeIntent]:
    # D1 policy: intents come only from strategy signals — no forced minimum;
    # min_trades is retained for call compatibility until P7 cleans it up.
    del min_trades
    account_id = account.id
    risk_policy = str(account.risk_policy).strip().lower()
    stop_loss_pct = account.stop_loss_pct
    take_profit_pct = account.take_profit_pct
    instrument_mode = str(account.instrument_mode).strip().lower()

    sleeve_repo = SleeveRepository(conn)
    all_sleeves = sleeve_repo.fetch_for_account(account_id=account_id)
    active_sleeves = [s for s in all_sleeves if s.status.strip().lower() == "active"]
    if not active_sleeves:
        return []

    max_intents = min(max_trades, len(active_sleeves))
    intents: list[SleeveTradeIntent] = []
    for sleeve in active_sleeves:
        if len(intents) >= max_intents:
            break
        assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve.id)
        if assignment is None:
            # A book with no assigned strategy does not trade — no account fallback.
            continue
        strategy_name = assignment.strategy_name.strip()
        param_set_id = assignment.param_set_id
        if sleeve.trade_universes:
            sleeve_names: object = json.loads(sleeve.trade_universes)
            if isinstance(sleeve_names, list) and sleeve_names:
                effective_universe = resolve_named_universes([str(n) for n in sleeve_names])
            else:
                effective_universe = universe
        else:
            effective_universe = universe
        book_id = book_id_for_sleeve(conn, sleeve.id, create=True)
        assert book_id is not None
        state = _build_sleeve_state(conn, book_id=book_id)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sell = auto_trader_policy.choose_sell_ticker_by_risk(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )
        selection = _prepare_trade_selection(
            account,
            strategy_name,
            state,
            forced_sell,
            effective_universe,
            prices,
            histories or {},
            iv_rank_proxy,
            instrument_mode,
            fee,
            feature_history_fn=feature_history_fn,
        )
        if selection is None:
            continue
        side, symbol, qty, requested_price, delta_est, iv_est = selection
        intents.append(
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve.id,
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
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
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
            histories=histories,
            feature_history_fn=feature_history_fn,
        )
    )
