from __future__ import annotations

import sqlite3

import pytest

from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.ledger.queries import load_account_state
from trading.services.fixtures.profiles import DEMO_PROFILE, SANDBOX_PROFILE, FixtureProfile
from trading.services.fixtures.seeding import seed_fixture_database

# Tables a generated sandbox is knowingly allowed to leave empty, each with the
# reason. This mapping is the review record for fixture coverage: when a
# migration adds a table, the coverage test fails until the table is either
# seeded or listed here deliberately.
KNOWN_EMPTY_SANDBOX_TABLES = {
    # The optimizer and walk-forward engines produce these; seeding them means
    # running a real sweep, which the fixture does not yet do.
    "optimization_experiments": "requires a real optimizer sweep",
    "optimization_run_manifests": "requires a real optimizer sweep",
    "optimization_trials": "requires a real optimizer sweep",
    "optimization_windows": "requires a real optimizer sweep",
    # Written by the risk and rotation runtime passes, which the seeder does not
    # yet drive. The next widening step for the sandbox profile.
    "risk_snapshots": "requires driving the risk pass",
    "risk_decisions": "requires driving the risk pass",
    "rotation_decisions": "requires driving the rotation engine",
    # No code reads or writes it; its repository and record were deleted
    # 2026-08-10. Drop the table in the migration squash.
    "feature_providers": "unused table awaiting removal",
}


@pytest.fixture
def demo_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    seed_fixture_database(conn, profile=DEMO_PROFILE, provider=DemoMarketDataProvider())
    return conn


def _data_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def test_demo_seed_derives_daily_metrics_through_the_real_writer(demo_conn: sqlite3.Connection) -> None:
    """The fixture must produce daily_metrics via the production writer, not fabricate them.

    Guards the "fixtures consume real code" property: the metrics come from the
    seeded equity curve + fills, so a generated database can never display values
    the live system cannot compute — and honestly-unavailable columns stay NULL.
    """
    rows = demo_conn.execute(
        "SELECT return_pct, trade_count, hit_rate, drawdown_pct, risk_adjusted_score FROM daily_metrics"
    ).fetchall()
    assert rows, "the fixture should have written daily_metrics rows"

    # return_pct is derived from the seeded equity curve on days that have a prior snapshot.
    assert any(row[0] is not None for row in rows)
    # The seeded fills mean some days record trades.
    assert any((row[1] or 0) > 0 for row in rows)
    # risk_adjusted_score is a real derived column: the trailing writer fills it in
    # once the seeded equity curve has accumulated enough daily returns.
    assert any(row[4] is not None for row in rows), "risk_adjusted_score should be derived"
    # hit_rate is now derived on days with a closing trade, because seeded sells go
    # through the real fill path and persist realized_pnl_delta on the order.
    assert any(row[2] is not None for row in rows), "hit_rate should be derived on closing-trade days"
    # drawdown_pct stays NULL — it has no honest data source at this grain.
    assert all(row[3] is None for row in rows), "drawdown_pct must be NULL"


def test_seeded_fills_reconcile_with_book_accounting(demo_conn: sqlite3.Connection) -> None:
    """Replayed account state must equal the books' persisted balances.

    The fixture used to write orders directly and hand-write positions and
    balances, which let the tables contradict each other. Routing fills through
    the production path makes cash, positions, and the ledger derived, so the
    two views of the same account have to agree.
    """
    accounts = demo_conn.execute("SELECT id, name, initial_cash FROM accounts").fetchall()
    assert accounts

    for account in accounts:
        state = load_account_state(
            demo_conn,
            account_id=int(account["id"]),
            initial_cash=float(account["initial_cash"]),
        )
        books = BookRepository(demo_conn).fetch_for_account(account_id=int(account["id"]))
        assert sum(book.current_cash for book in books) == pytest.approx(state.cash, abs=0.01)

        held: dict[str, float] = {}
        for book in books:
            for position in PositionRepository(demo_conn).fetch_for_book(book_id=book.id):
                held[position.symbol] = held.get(position.symbol, 0.0) + position.qty
        assert held == pytest.approx(state.positions)


def test_seeded_fills_write_ledger_entries(demo_conn: sqlite3.Connection) -> None:
    """Each seeded fill lands cash-flow ledger entries, as a real fill does."""
    fills = demo_conn.execute("SELECT COUNT(*) FROM order_fills").fetchone()[0]
    trade_entries = demo_conn.execute("SELECT COUNT(*) FROM ledger WHERE entry_type = 'trade'").fetchone()[0]
    fee_entries = demo_conn.execute("SELECT COUNT(*) FROM ledger WHERE entry_type = 'fee'").fetchone()[0]
    assert trade_entries == fills
    assert fee_entries == fills, "a non-zero commission must produce a fee entry per fill"


def test_every_snapshot_row_is_internally_consistent(demo_conn: sqlite3.Connection) -> None:
    """equity must equal cash + market_value on every snapshot the fixture writes."""
    inconsistent = demo_conn.execute(
        "SELECT COUNT(*) FROM equity_snapshots WHERE ABS(equity - (cash + market_value)) > 0.01"
    ).fetchone()[0]
    assert inconsistent == 0


def test_opening_balance_is_not_recorded_as_a_deposit(demo_conn: sqlite3.Connection) -> None:
    """Opening cash lives in accounts.initial_cash, never as a ledger deposit.

    Writing one would double-count the opening balance, since account-state
    replay already starts from initial_cash.
    """
    deposits = demo_conn.execute("SELECT COUNT(*) FROM ledger WHERE entry_type = 'deposit'").fetchone()[0]
    assert deposits == 0, "the demo profile has no mid-life cash events, so it must have no deposits"


def test_fixture_accounts_are_never_live_enabled(demo_conn: sqlite3.Connection) -> None:
    """Live Trading Safety Guard: a seeder must never leave live trading on."""
    rows = demo_conn.execute("SELECT live_trading_enabled, broker_type FROM accounts").fetchall()
    assert rows
    assert all(int(row[0]) == 0 for row in rows)
    assert all(str(row[1]) == "paper" for row in rows)


@pytest.mark.parametrize("profile", [DEMO_PROFILE, SANDBOX_PROFILE], ids=lambda profile: profile.name)
def test_profiles_seed_without_overdrawing(conn: sqlite3.Connection, profile: FixtureProfile) -> None:
    """Every profile builds, and no book is left holding negative cash."""
    seed_fixture_database(conn, profile=profile, provider=DemoMarketDataProvider())
    negative = conn.execute("SELECT COUNT(*) FROM books WHERE current_cash < 0").fetchone()[0]
    assert negative == 0


@pytest.mark.parametrize("profile", [DEMO_PROFILE, SANDBOX_PROFILE], ids=lambda profile: profile.name)
def test_book_start_equity_sums_to_the_accounts_opening_capital(
    conn: sqlite3.Connection, profile: FixtureProfile
) -> None:
    """Σ books.start_equity must equal accounts.initial_cash.

    Funding a sleeve carves capital out of the default book rather than adding
    it, so the opening capital has to stay conserved across the split. When the
    carve-out debited only the balances, the default book kept the account's
    whole opening figure as its basis and reported a loss the size of the
    sleeves — and any account-level return measured against Σ start_equity
    would have been wrong by the same amount.
    """
    seed_fixture_database(conn, profile=profile, provider=DemoMarketDataProvider())

    mismatched = conn.execute(
        """SELECT a.name, a.initial_cash, SUM(b.start_equity) AS booked
           FROM accounts a JOIN books b ON b.account_id = a.id
           GROUP BY a.id
           HAVING ABS(a.initial_cash - booked) > 0.01"""
    ).fetchall()
    assert not mismatched, f"opening capital drifted across books: {[tuple(row) for row in mismatched]}"


def test_sandbox_seeds_cash_events_through_the_ledger(conn: sqlite3.Connection) -> None:
    """Mid-life deposits and withdrawals are the only way total_deposited moves."""
    seed_fixture_database(conn, profile=SANDBOX_PROFILE, provider=DemoMarketDataProvider())
    deposits = conn.execute("SELECT COUNT(*) FROM ledger WHERE entry_type = 'deposit'").fetchone()[0]
    withdrawals = conn.execute("SELECT COUNT(*) FROM ledger WHERE entry_type = 'withdrawal'").fetchone()[0]
    assert deposits >= 1
    assert withdrawals >= 1


def test_sandbox_profile_covers_every_table_but_the_known_gaps(conn: sqlite3.Connection) -> None:
    """A sandbox build must populate every table it does not knowingly skip.

    The fixture's own coverage gate: a new table arriving via migration fails
    here until someone decides whether the sandbox should seed it.
    """
    seed_fixture_database(conn, profile=SANDBOX_PROFILE, provider=DemoMarketDataProvider())

    empty = {
        table
        for table in _data_tables(conn)
        if conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0  # noqa: S608
    }
    unexpected = sorted(empty - set(KNOWN_EMPTY_SANDBOX_TABLES))
    assert not unexpected, (
        f"sandbox left {unexpected} empty; seed them or record the reason in KNOWN_EMPTY_SANDBOX_TABLES"
    )

    stale = sorted(set(KNOWN_EMPTY_SANDBOX_TABLES) - empty)
    assert not stale, f"{stale} are now seeded; remove them from KNOWN_EMPTY_SANDBOX_TABLES"
