from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Mapping

import pandas as pd

import trading.domain.auto_trading_policy as auto_trader_policy
from trading.models import AccountRecord
from trading.models.execution.book_trade_candidate import BookTradeCandidate
from trading.models.execution.book_trade_state import BookTradeState
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.universe import resolve_named_universes

if TYPE_CHECKING:
    from trading.services.auto_trading.execution import FeatureHistoryFn


def _prepare_trade_selection(*args, **kwargs):
    from trading.services.auto_trading.execution import prepare_trade_selection

    return prepare_trade_selection(*args, **kwargs)


def _build_book_state(conn: sqlite3.Connection, *, book_id: int) -> BookTradeState:
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
    return BookTradeState(
        cash=float(current_cash),
        positions=positions,
        avg_cost=avg_cost,
    )


def generate_book_trade_intents(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    max_trades: int,
    fee: float,
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> list[BookTradeCandidate]:
    # D1 policy: intents come only from strategy signals — no forced minimum.
    account_id = account.id
    risk_policy = str(account.risk_policy).strip().lower()
    stop_loss_pct = account.stop_loss_pct
    take_profit_pct = account.take_profit_pct
    instrument_mode = str(account.instrument_mode).strip().lower()

    # Book-native enumeration (SR-2): active, non-default, openly assigned books.
    # Unassigned or non-active books do not trade — no account fallback.
    trading_books = enumerate_trading_books(conn, account_id=account_id)
    if not trading_books:
        return []

    max_intents = min(max_trades, len(trading_books))
    intents: list[BookTradeCandidate] = []
    for trading_book in trading_books:
        if len(intents) >= max_intents:
            break
        book = trading_book.book
        book_id = book.id
        strategy_name = trading_book.assignment.strategy_name.strip()
        param_set_id = trading_book.assignment.param_set_id
        if book.trade_universes:
            book_universe_names: object = json.loads(book.trade_universes)
            if isinstance(book_universe_names, list) and book_universe_names:
                effective_universe = resolve_named_universes([str(n) for n in book_universe_names])
            else:
                effective_universe = universe
        else:
            effective_universe = universe
        state = _build_book_state(conn, book_id=book_id)
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
            BookTradeCandidate(
                account_id=account_id,
                book_id=book_id,
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


def run_multi_book_mode_for_account(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    max_trades: int,
    fee: float,
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> int:
    return len(
        generate_book_trade_intents(
            conn,
            account=account,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            max_trades=max_trades,
            fee=fee,
            histories=histories,
            feature_history_fn=feature_history_fn,
        )
    )
