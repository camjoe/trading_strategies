from __future__ import annotations

import json
import logging
import sqlite3
from typing import Mapping

import pandas as pd

import trading.domain.auto_trading_policy as auto_trader_policy
from trading.models import AccountRecord
from trading.models.execution import BookTradeCandidate, BookTradeState
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.execution.selection.selection import FeatureHistoryFn, prepare_book_trades
from trading.services.strategy_catalog.resolution import (
    UnknownCatalogStrategyError,
    resolve_catalog_strategy,
)

logger = logging.getLogger(__name__)


def _build_book_state(conn: sqlite3.Connection, *, book_id: int) -> BookTradeState:
    # A book's live state (cash + holdings) is authoritative — the submission path
    # maintains book balances and positions through the shared execution service.
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
    histories: Mapping[str, pd.DataFrame] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
    selection_seed: str = "",
) -> list[BookTradeCandidate]:
    # Intents come only from strategy signals — no forced minimum; a run with no
    # signals produces no trades.
    account_id = account.id

    # Book-native enumeration: active, openly assigned books — including the
    # default book, which trades like any other (ADR 010/014). Unassigned or
    # non-active books do not trade; there is no account fallback.
    trading_books = enumerate_trading_books(conn, account_id=account_id)
    if not trading_books:
        return []

    # `max_trades` caps trades for the account, not books. Book order therefore
    # decides who gets that budget — and again downstream, where the risk gate
    # consumes its account caps in intent order — so it is rotated per run.
    books_by_id = {trading_book.book.id: trading_book for trading_book in trading_books}
    claim_order = auto_trader_policy.order_capacity_claimants(list(books_by_id), seed=selection_seed)

    intents: list[BookTradeCandidate] = []
    for trading_book in (books_by_id[book_id] for book_id in claim_order):
        remaining = max_trades - len(intents)
        if remaining <= 0:
            break
        book = trading_book.book
        book_id = book.id
        strategy_name = trading_book.assignment.strategy_name.strip()
        try:
            resolved = resolve_catalog_strategy(conn, strategy_name)
        except UnknownCatalogStrategyError:
            logger.warning(
                "Book %s: strategy %r does not resolve to a code primitive; skipping (no trades).",
                book_id,
                strategy_name,
            )
            continue
        # Signals resolve through the catalog row's canonical primitive,
        # so a data variant runs the right primitive; the intent keeps the
        # assigned label for display and rotation bookkeeping.
        signal_primitive = resolved.primitive
        strategy_params = resolved.params
        book_symbols: object = json.loads(book.trade_symbols) if book.trade_symbols else []
        if isinstance(book_symbols, list) and book_symbols:
            effective_universe = [str(symbol) for symbol in book_symbols]
        else:
            effective_universe = universe
        # Execution/risk knobs are book-owned (revision 0004).
        risk_policy = book.risk_policy.strip().lower()
        instrument_mode = book.instrument_mode.strip().lower()
        state = _build_book_state(conn, book_id=book_id)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sells = auto_trader_policy.order_risk_breaches(
            can_sell,
            prices,
            state,
            risk_policy,
            book.stop_loss_pct,
            book.take_profit_pct,
        )
        # A book's own limit binds within whatever the account has left;
        # NULL means the book adds no limit of its own.
        book_budget = remaining if book.max_trades_per_run is None else min(remaining, book.max_trades_per_run)
        # The book is the settings mapping: option/leaps knobs are book
        # columns since revision 0005.
        selections = prepare_book_trades(
            book,
            signal_primitive,
            strategy_params,
            state,
            forced_sells,
            effective_universe,
            prices,
            histories or {},
            iv_rank_proxy,
            instrument_mode,
            fee,
            max_trades=book_budget,
            trade_size_pct=book.trade_size_pct,
            max_position_pct=book.max_position_pct,
            feature_history_fn=feature_history_fn,
            selection_seed=selection_seed,
        )
        forced_sell_set = set(forced_sells)
        for side, symbol, qty, requested_price, delta_est, iv_est in selections:
            intents.append(
                BookTradeCandidate(
                    account_id=account_id,
                    book_id=book_id,
                    strategy_name=strategy_name,
                    side=side,
                    symbol=symbol,
                    qty=qty,
                    requested_price=requested_price,
                    # Only the sells that actually breached carry the flag.
                    forced_sell=symbol if side == "sell" and symbol in forced_sell_set else None,
                    delta_est=delta_est,
                    iv_est=iv_est,
                )
            )
    return intents
