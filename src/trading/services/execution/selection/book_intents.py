from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from trading.domain.auto_trading.exits import order_risk_breaches
from trading.domain.auto_trading.fairness import order_capacity_claimants, split_trade_budget
from trading.models import AccountRecord
from trading.models.execution import BookTradeCandidate, BookTradeState
from trading.models.market_data import MarketInputs
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.execution.selection.selection import FeatureHistoryFn, TradeSelection, prepare_book_trades
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
        # Selection is float policy math; convert the Decimal position at this edge.
        positions[pos.symbol] = float(pos.qty)
        avg_cost[pos.symbol] = float(pos.avg_cost)
    return BookTradeState(
        cash=float(current_cash),
        positions=positions,
        avg_cost=avg_cost,
    )


@dataclass
class _BookSelection:
    """One book's selection for the run, and how to redo it for a smaller budget."""

    strategy_name: str
    forced_sells: set[str]
    selections: list[TradeSelection]
    reselect: Callable[[int], list[TradeSelection]]


def _share_account_budget(selected_by_book: dict[int, _BookSelection], *, max_trades: int) -> dict[int, int]:
    """Split the account cap across books, serving risk-breach exits before anything else.

    Forced sells head each book's list, so a share that covers them keeps them.
    """
    forced_demand = {
        book_id: sum(1 for side, symbol, *_ in chosen.selections if side == "sell" and symbol in chosen.forced_sells)
        for book_id, chosen in selected_by_book.items()
    }
    urgent = split_trade_budget(forced_demand, budget=max_trades)
    rest = split_trade_budget(
        {book_id: len(chosen.selections) - forced_demand[book_id] for book_id, chosen in selected_by_book.items()},
        budget=max_trades - sum(urgent.values()),
    )
    return {book_id: urgent[book_id] + rest[book_id] for book_id in selected_by_book}


def generate_book_trade_intents(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    market: MarketInputs,
    max_trades: int,
    fee: float,
    feature_history_fn: FeatureHistoryFn | None = None,
    selection_seed: str = "",
) -> list[BookTradeCandidate]:
    # Intents come only from strategy signals — no forced minimum; a run with no
    # signals produces no trades.
    account_id = account.id
    if max_trades <= 0:
        return []

    # Book-native enumeration: active, openly assigned books — including the
    # default book, which trades like any other (ADR 010/014). Unassigned or
    # non-active books do not trade; there is no account fallback.
    trading_books = enumerate_trading_books(conn, account_id=account_id)
    if not trading_books:
        return []

    # `max_trades` caps trades for the account, not books. Each book selects up to
    # its own limit, then the budget is shared across books one trade at a time
    # (`split_trade_budget`), so a book is not starved by the books before it.
    # Risk-breach exits are served first, then the rest one trade at a time. Claim order,
    # rotated per run, decides who gets any odd trade — and, downstream, the order in which
    # the risk gate consumes its account caps.
    books_by_id = {trading_book.book.id: trading_book for trading_book in trading_books}
    claim_order = order_capacity_claimants(list(books_by_id), seed=selection_seed)

    selected_by_book: dict[int, _BookSelection] = {}
    for trading_book in (books_by_id[book_id] for book_id in claim_order):
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
        # An empty book universe selects over the whole run universe; the fetch
        # side reads the same empty list as contributing nothing.
        effective_universe = book.trade_symbol_list() or market.universe
        # Execution/risk knobs are book-owned (revision 0004).
        risk_policy = book.risk_policy.strip().lower()
        instrument_mode = book.instrument_mode.strip().lower()
        state = _build_book_state(conn, book_id=book_id)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty > 0]
        forced_sells = order_risk_breaches(
            can_sell,
            market.prices,
            state,
            risk_policy,
            book.stop_loss_pct,
            book.take_profit_pct,
        )
        # A book's own limit binds within the account cap; NULL means the book
        # adds no limit of its own.
        book_budget = max_trades if book.max_trades_per_run is None else min(max_trades, book.max_trades_per_run)

        # The book is the settings mapping: option/leaps knobs are book
        # columns since revision 0005.
        def select(
            budget: int,
            book=book,
            signal_primitive=signal_primitive,
            strategy_params=strategy_params,
            state=state,
            forced_sells=forced_sells,
            effective_universe=effective_universe,
            instrument_mode=instrument_mode,
        ) -> list[TradeSelection]:
            return prepare_book_trades(
                book,
                signal_primitive,
                strategy_params,
                state,
                forced_sells,
                effective_universe,
                market.prices,
                market.histories,
                market.iv_rank_proxy,
                instrument_mode,
                fee,
                max_trades=budget,
                trade_size_pct=book.trade_size_pct,
                max_position_pct=book.max_position_pct,
                feature_history_fn=feature_history_fn,
                selection_seed=selection_seed,
            )

        selected_by_book[book_id] = _BookSelection(strategy_name, set(forced_sells), select(book_budget), select)

    shares = _share_account_budget(selected_by_book, max_trades=max_trades)
    for book_id, chosen in selected_by_book.items():
        if shares[book_id] < len(chosen.selections):
            logger.info(
                "Book %s: %d trades selected, %d granted by the account cap of %d.",
                book_id,
                len(chosen.selections),
                shares[book_id],
                max_trades,
            )
            # Buys were funded for the full selection; size them again for the trades granted.
            chosen.selections = chosen.reselect(shares[book_id])
    intents: list[BookTradeCandidate] = []
    for book_id, chosen in selected_by_book.items():
        strategy_name, forced_sell_set = chosen.strategy_name, chosen.forced_sells
        for side, symbol, qty, requested_price, delta_est, iv_est in chosen.selections:
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
