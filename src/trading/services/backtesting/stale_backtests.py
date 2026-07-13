"""Enumerate strategies whose backtest evidence is stale or missing.

The remediation counterpart to the backtest freshness diagnostic: for each account,
the candidate strategy set rotation could promote (each active book's incumbent
plus its challenger schedule) is checked against the same
``assess_backtest_freshness`` policy. A strategy is a target when it has no
backtest at all (missing) or its newest backtest is stale.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.coercion import row_str
from common.time import utc_now_iso
from trading.backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_latest_backtest_run_id_for_account_strategy,
)
from trading.domain.backtest_freshness import (
    DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS,
    assess_backtest_freshness,
)
from trading.domain.strategy_signals import resolve_strategy
from trading.models.accounts.account_record import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.books.rotation import resolve_book_rotation_schedule

# Reasons a (account, strategy) pair needs a fresh backtest.
REASON_MISSING = "missing"
REASON_STALE = "stale"


@dataclass(frozen=True)
class StaleBacktestTarget:
    """A strategy whose backtest evidence needs refreshing for one account."""

    account_name: str
    account_id: int
    strategy_name: str
    age_days: float | None  # None when there is no backtest (missing)
    reason: str  # REASON_MISSING | REASON_STALE


def _canonical_strategy_key(name: str) -> str:
    """The catalog key a backtest is stored under, so freshness lookups match.

    Schedule entries may be aliases (e.g. ``macd_trend`` -> ``macd``);
    ``run_backtest`` persists the resolved ``strategy_id``. Unknown labels keep
    their lowercased form — they surface as missing and their backtest errors
    rather than looping.
    """
    try:
        return resolve_strategy(name).strategy_id
    except ValueError:
        return name.lower()


def _candidate_strategies(conn: sqlite3.Connection, account: AccountRecord) -> list[str]:
    """The strategies rotation could run for the account: each active book's
    incumbent, plus its challenger schedule when that book has rotation enabled.
    Names are canonicalized to their catalog key and deduplicated."""
    names: list[str] = []
    seen: set[str] = set()
    for trading_book in enumerate_trading_books(conn, account_id=account.id):
        candidates = [trading_book.assignment.strategy_name]
        schedule_config = resolve_book_rotation_schedule(conn, book_id=trading_book.book.id)
        if schedule_config.rotation_enabled:
            candidates.extend(schedule_config.schedule)
        for raw in candidates:
            if not raw.strip():
                continue
            key = _canonical_strategy_key(raw.strip())
            if key not in seen:
                seen.add(key)
                names.append(key)
    return names


def find_stale_backtests(
    conn: sqlite3.Connection,
    *,
    account_name: str | None = None,
    threshold_days: int = DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS,
    reference_iso: str | None = None,
) -> list[StaleBacktestTarget]:
    """Return the (account, strategy) pairs whose backtest is missing or stale.

    ``account_name`` limits the scan to one account; ``reference_iso`` overrides
    the "now" used for the age comparison (defaults to the current time).
    """
    reference = reference_iso or utc_now_iso()
    accounts = AccountRepository(conn).fetch_all()
    if account_name is not None:
        accounts = [account for account in accounts if account.name == account_name]

    targets: list[StaleBacktestTarget] = []
    for account in accounts:
        for strategy_name in _candidate_strategies(conn, account):
            created_at: str | None = None
            run_id = fetch_latest_backtest_run_id_for_account_strategy(
                conn, account_id=account.id, strategy_name=strategy_name
            )
            if run_id is not None:
                run = fetch_backtest_report_run(conn, run_id)
                created_at = row_str(run, "created_at") if run is not None else None
            freshness = assess_backtest_freshness(
                backtest_created_at=created_at,
                reference_iso=reference,
                threshold_days=threshold_days,
            )
            if not freshness.available:
                targets.append(StaleBacktestTarget(account.name, account.id, strategy_name, None, REASON_MISSING))
            elif freshness.is_stale:
                targets.append(
                    StaleBacktestTarget(account.name, account.id, strategy_name, freshness.age_days, REASON_STALE)
                )
    return targets
