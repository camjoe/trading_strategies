"""Build a deterministic synthetic database from a named fixture profile.

Every record a running system derives is written through the production writer
that owns it: fills through :func:`apply_book_fill`, cash events through
:func:`record_trade`, position marks through :func:`mark_book_to_market`, and
daily metrics through :func:`write_daily_metrics_for_account`. The seeder never
hand-writes derived state, so a generated database cannot show a value the live
system is incapable of producing.

Two consequences of that rule are worth knowing before editing this module:

- **Prices come from the injected market-data provider**, not from the profile.
  Seeded trades execute at the provider's close for the day they land on, so a
  generated database and the provider backing the running app agree on price.
- **Opening balances are not ledger deposits.** ``accounts.initial_cash`` carries
  the opening balance and account-state replay starts from it, so writing an
  opening deposit row as well would double-count it. Only genuine mid-life cash
  events reach the ledger.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

import pandas as pd

from common.constants import SETTLEMENT_TICKER
from common.time import as_utc_iso
from trading.models import AccountConfig
from trading.models.orders import OrderInsert
from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.books import BookRepository
from trading.repositories.feature_providers import FeatureProviderRepository
from trading.repositories.fixture_seed import FixtureSeedRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import create_account, get_account
from trading.services.analysis.daily_metrics import write_daily_metrics_for_account
from trading.services.books.book_assignments import assign_book_strategy
from trading.services.execution.ledger import record_trade
from trading.services.execution.nav import mark_account_to_market
from trading.services.execution.submission import apply_book_fill
from trading.services.fixtures.profiles import (
    FixtureAccount,
    FixtureBuy,
    FixtureProfile,
    FixtureTrade,
)
from trading.services.market_data import MarketDataProvider
from trading.services.operational_settings import set_runtime_throttle_settings
from trading.services.parameters import update_book_rotation_scheduling
from trading.services.universe import resolve_trade_symbols

# Snapshots are stamped at a nominal 16:00 UTC close so each business day has one
# unambiguous end-of-day time for the metrics writer to derive returns from.
SNAPSHOT_CLOSE_HOUR = 16

# A flat per-trade commission. Non-zero on purpose: a zero fee would leave the
# ledger's `fee` entries and the commission-aware cost-basis math unexercised.
FIXTURE_COMMISSION = 1.0

# Throttle values written to `global_settings` for profiles that seed it.
# Deliberately loose — the fixture is not exercising throttle rejection.
FIXTURE_MAX_TRADES_PER_DAY = 25
FIXTURE_MAX_TRADES_PER_MINUTE = 5

# The synthetic backtest's sample executions are keyed off snapshots this far
# inside the curve, so both land on days the curve actually covers.
_BACKTEST_EXECUTION_MARGIN_DAYS = 5


@dataclass
class _BookPlan:
    """A book being seeded, with the trades assigned to it."""

    book_id: int
    trades: tuple[FixtureTrade, ...]
    realized_pnl: float = 0.0


@dataclass
class _AccountPlan:
    account_id: int
    spec: FixtureAccount
    books: list[_BookPlan] = field(default_factory=list)


def _profile_symbols(profile: FixtureProfile) -> list[str]:
    symbols = {
        trade.symbol
        for account in profile.accounts
        for trade in (*account.trades, *(t for book in account.extra_books for t in book.trades))
    }
    return sorted(symbols)


def _snapshot_time(stamp: pd.Timestamp) -> str:
    return as_utc_iso(datetime.combine(stamp.date(), time(hour=SNAPSHOT_CLOSE_HOUR), tzinfo=timezone.utc))


def _create_accounts(conn: sqlite3.Connection, profile: FixtureProfile, *, now_iso: str) -> list[_AccountPlan]:
    """Create every account, its bootstrapped default book, and any extra books."""
    repo = FixtureSeedRepository(conn)
    plans: list[_AccountPlan] = []
    for spec in profile.accounts:
        create_account(
            conn,
            spec.name,
            spec.strategy,
            spec.initial_cash,
            spec.benchmark,
            AccountConfig(
                descriptive_name=spec.descriptive_name,
                trade_universes=list(spec.trade_universes),
            ),
        )
        account_id = repo.account_id(spec.name)
        # Every generated account is paper with live trading off; the Live
        # Trading Safety Guard forbids a seeder ever leaving it otherwise.
        repo.set_account_paper_safety(account_id, now_iso=now_iso)

        default_book_id = repo.default_book_id(account_id)
        plan = _AccountPlan(account_id=account_id, spec=spec)
        plan.books.append(_BookPlan(book_id=default_book_id, trades=spec.trades))
        for extra in spec.extra_books:
            book_id = repo.fund_additional_book(
                account_id=account_id,
                default_book_id=default_book_id,
                name=extra.name,
                trade_symbols=dumps_json_column(resolve_trade_symbols(list(spec.trade_universes))),
                opening_cash=extra.opening_cash,
                now_iso=now_iso,
            )
            assign_book_strategy(conn, book_id=book_id, strategy_name=extra.strategy, now_iso=now_iso)
            plan.books.append(_BookPlan(book_id=book_id, trades=extra.trades))
        plans.append(plan)
    return plans


def _resolve_fill_quantity(
    conn: sqlite3.Connection,
    *,
    trade: FixtureTrade,
    book_id: int,
    price: float,
) -> float:
    """Whole-share quantity for a trade, or 0.0 when it cannot be placed.

    Floored to whole shares so a generated book never holds a fractional
    position the equity brokers in this system would not produce.
    """
    if isinstance(trade, FixtureBuy):
        return float(math.floor(trade.notional / price))
    position = PositionRepository(conn).fetch(book_id=book_id, symbol=trade.symbol)
    if position is None:
        return 0.0
    return float(math.floor(position.qty * trade.fraction))


def _apply_fill(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    account_id: int,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    when_iso: str,
) -> None:
    """Record a filled order and apply it through the production fill path.

    Mirrors what :func:`record_trade` does for the default book, but takes an
    explicit ``book_id`` so non-default books trade too.
    """
    orders = OrderRepository(conn)
    with unit_of_work(conn):
        order_id = orders.insert(
            OrderInsert(
                book_id=book_id,
                account_id=account_id,
                symbol=symbol,
                side=side,
                qty=qty,
                requested_price=price,
                status="filled",
                filled_qty=qty,
                avg_fill_price=price,
                commission=FIXTURE_COMMISSION,
                submitted_at=when_iso,
                updated_at=when_iso,
            )
        )
        orders.insert_fill(
            order_id=order_id,
            filled_qty=qty,
            fill_price=price,
            fill_time=when_iso,
            commission=FIXTURE_COMMISSION,
            exec_id=f"fixture:{order_id}",
        )
        apply_book_fill(
            conn,
            book_id=book_id,
            order_id=order_id,
            side=side,
            symbol=symbol,
            fill_qty=qty,
            fill_price=price,
            transaction_cost=FIXTURE_COMMISSION,
            fill_time=when_iso,
        )


def _place_day_trades(
    conn: sqlite3.Connection,
    *,
    plan: _AccountPlan,
    book: _BookPlan,
    day_index: int,
    prices: dict[str, float],
    when_iso: str,
    date_text: str,
) -> None:
    """Apply the book's trades for one business day and accrue realized P&L."""
    due = [trade for trade in book.trades if trade.day_index == day_index]
    if not due:
        return

    for trade in due:
        price = prices[trade.symbol]
        qty = _resolve_fill_quantity(conn, trade=trade, book_id=book.book_id, price=price)
        if qty <= 0:
            continue
        if isinstance(trade, FixtureBuy):
            record = BookRepository(conn).fetch_by_id(book_id=book.book_id)
            assert record is not None
            cost = qty * price + FIXTURE_COMMISSION
            if cost > record.current_cash:
                raise ValueError(
                    f"Fixture profile overdraws book {book.book_id} on day {day_index}: "
                    f"{trade.symbol} costs {cost:.2f} against {record.current_cash:.2f} cash."
                )
        _apply_fill(
            conn,
            book_id=book.book_id,
            account_id=plan.account_id,
            symbol=trade.symbol,
            side="buy" if isinstance(trade, FixtureBuy) else "sell",
            qty=qty,
            price=price,
            when_iso=when_iso,
        )

    # A sell persists its realized P&L on the order; roll the day's closings into
    # the book's running total so the equity snapshot can report it.
    for order in OrderRepository(conn).fetch_filled_for_book_on_date(book_id=book.book_id, date_str=date_text):
        book.realized_pnl += order.realized_pnl_delta or 0.0


def _write_book_snapshot(conn: sqlite3.Connection, *, book: _BookPlan, when_iso: str) -> None:
    """Snapshot a book from its marked state — never from fabricated numbers."""
    record = BookRepository(conn).fetch_by_id(book_id=book.book_id)
    assert record is not None
    positions = PositionRepository(conn).fetch_for_book(book_id=book.book_id)
    market_value = sum(position.market_value for position in positions)
    unrealized = sum(position.unrealized_pnl for position in positions)
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book.book_id,
        snapshot_time=when_iso,
        cash=record.current_cash,
        market_value=market_value,
        equity=record.current_cash + market_value,
        realized_pnl=book.realized_pnl,
        unrealized_pnl=unrealized,
    )


def _apply_cash_events(conn: sqlite3.Connection, *, plan: _AccountPlan, day_index: int, when_iso: str) -> None:
    """Post the account's deposits and withdrawals falling on this day."""
    for event in plan.spec.cash_events:
        if event.day_index != day_index:
            continue
        # A settlement-ticker trade is how the app records a cash event: a buy
        # deposits, a sell withdraws.
        record_trade(
            conn,
            plan.spec.name,
            "buy" if event.amount > 0 else "sell",
            SETTLEMENT_TICKER,
            abs(event.amount),
            1.0,
            0.0,
            when_iso,
            None,
        )


def _run_history(
    conn: sqlite3.Connection,
    *,
    plans: list[_AccountPlan],
    business_days: list[pd.Timestamp],
    closes: pd.DataFrame,
    symbols: list[str],
) -> None:
    """Walk the story day by day: trade, mark to market, snapshot, derive metrics."""
    for day_index, stamp in enumerate(business_days):
        when_iso = _snapshot_time(stamp)
        date_text = stamp.date().isoformat()
        prices = {symbol: float(closes.iloc[day_index][symbol]) for symbol in symbols}

        for plan in plans:
            _apply_cash_events(conn, plan=plan, day_index=day_index, when_iso=when_iso)
            for book in plan.books:
                _place_day_trades(
                    conn,
                    plan=plan,
                    book=book,
                    day_index=day_index,
                    prices=prices,
                    when_iso=when_iso,
                    date_text=date_text,
                )

            mark_account_to_market(conn, account_id=plan.account_id, prices=prices, as_of=when_iso)
            for book in plan.books:
                _write_book_snapshot(conn, book=book, when_iso=when_iso)

            # The snapshots just written are the end-of-day equity the metrics
            # derive return from, so this must follow them.
            write_daily_metrics_for_account(
                conn,
                get_account(conn, plan.spec.name),
                metric_date=date_text,
                now_iso=when_iso,
            )


def _seed_research_records(
    conn: sqlite3.Connection,
    *,
    profile: FixtureProfile,
    plans: list[_AccountPlan],
    now_iso: str,
) -> None:
    """Backtest runs and promotion reviews for the accounts the profile names."""
    repo = FixtureSeedRepository(conn)
    snapshots = EquitySnapshotRepository(conn)
    by_name = {plan.spec.name: plan for plan in plans}

    for account_name in profile.backtest_accounts:
        plan = by_name[account_name]
        history = snapshots.fetch_history(account_id=plan.account_id, limit=profile.business_days)
        curve = sorted((row.snapshot_time[:10], row.equity) for row in history)
        if len(curve) <= _BACKTEST_EXECUTION_MARGIN_DAYS * 2:
            raise ValueError(f"Profile '{profile.name}' is too short to anchor a fixture backtest curve.")
        repo.insert_backtest(
            account_id=plan.account_id,
            strategy_key=plan.spec.strategy,
            start_date=curve[0][0],
            end_date=curve[-1][0],
            snapshots=curve,
            now_iso=now_iso,
        )

    for account_name in profile.promotion_review_accounts:
        plan = by_name[account_name]
        repo.insert_promotion_review(
            account_id=plan.account_id,
            account_name=account_name,
            strategy_key=plan.spec.strategy,
            now_iso=now_iso,
        )


def _seed_settings(conn: sqlite3.Connection, *, profile: FixtureProfile, now_iso: str) -> None:
    """Operational settings tables.

    Kept outside the main unit of work: the rotation-scheduling writer resolves
    its book through a path that commits, which would close an enclosing
    transaction early.
    """
    if profile.seed_global_settings:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=FIXTURE_MAX_TRADES_PER_DAY,
            runtime_max_trades_per_minute=FIXTURE_MAX_TRADES_PER_MINUTE,
            updated_at=now_iso,
        )

    for provider_key in profile.feature_providers:
        FeatureProviderRepository(conn).upsert(
            provider_key=provider_key,
            enabled=1,
            config_json=dumps_json_column({"source": "fixture"}),
            created_at=now_iso,
            updated_at=now_iso,
        )

    for account in profile.accounts:
        if account.rotation is None:
            continue
        update_book_rotation_scheduling(
            conn,
            account_name=account.name,
            updates={
                "rotation_enabled": account.rotation.enabled,
                "rotation_schedule": list(account.rotation.challengers),
                "rotation_lookback_days": account.rotation.lookback_days,
            },
        )


def seed_fixture_database(
    conn: sqlite3.Connection,
    *,
    profile: FixtureProfile,
    provider: MarketDataProvider,
    anchor_date: date | None = None,
) -> None:
    """Seed *conn* with the story described by *profile*, priced by *provider*."""
    anchor = anchor_date or datetime.now(timezone.utc).date()
    business_days = list(pd.bdate_range(end=anchor, periods=profile.business_days))
    now_iso = _snapshot_time(business_days[-1])
    symbols = _profile_symbols(profile)
    closes = provider.fetch_close_history(symbols, business_days[0].date(), business_days[-1].date())

    with unit_of_work(conn):
        plans = _create_accounts(conn, profile, now_iso=now_iso)
        _run_history(conn, plans=plans, business_days=business_days, closes=closes, symbols=symbols)
        _seed_research_records(conn, profile=profile, plans=plans, now_iso=now_iso)

    _seed_settings(conn, profile=profile, now_iso=now_iso)
