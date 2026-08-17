"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict

from common.coercion import row_expect_int
from common.time import parse_utc_iso, utc_now_iso
from trading.domain.broker_connection import BrokerConnection
from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.domain.market.hours import is_regular_us_equity_market_open
from trading.models import AccountRecord
from trading.models.execution import (
    AccountRunResult,
    BookRunAudit,
    BookTradeIntent,
    RiskGateConfig,
    RiskGateDecision,
)
from trading.models.market_data import MarketInputs
from trading.services.accounts.mutations import get_account
from trading.services.books.rotation.account_rotation import run_account_book_rotations
from trading.services.books.sector_config import load_symbol_sector_map
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_BROKER_API_ANOMALY,
    KILL_SWITCH_REASON_UNPRICED_POSITION,
)
from trading.services.execution.equity_reconciliation import reconcile_book_equity
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.nav import mark_account_to_market
from trading.services.execution.pre_submit_gate import BookPreSubmitGate
from trading.services.execution.risk import persist_book_run_audit
from trading.services.execution.selection.book_intents import generate_book_trade_intents
from trading.services.execution.selection.selection import (
    FeatureHistoryFn,
    build_feature_history_fn,
)
from trading.services.execution.submission import submit_book_intents
from trading.services.operational_settings.enforcement import enforce_runtime_trade_throttles

# Risk-decision reason when the global trade throttle blocks further submissions.
RISK_REASON_TRADE_THROTTLE_EXCEEDED = "trade_throttle_exceeded"


def is_runtime_submission_window_open(now_iso: str | None = None) -> bool:
    """Whether the runtime may submit orders right now (US regular equity hours).

    Public so callers can report *why* a run submitted nothing instead of
    reporting an indistinguishable zero-trade result.
    """
    return is_regular_us_equity_market_open(parse_utc_iso(now_iso or utc_now_iso()))


def _account_run_result(account: AccountRecord, audit: BookRunAudit) -> AccountRunResult:
    return AccountRunResult(
        account_name=str(account.name),
        submitted_count=audit.submitted_count,
        kill_switch_reasons=tuple(audit.kill_switch_reasons),
    )


def _risk_decisions_from_gate(decisions: list[RiskGateDecision]) -> list[dict[str, object]]:
    """Convert the gate's book-keyed decisions into audit dicts."""
    return [asdict(decision) for decision in decisions]


def _run_books_for_account(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    market: MarketInputs,
    max_trades: int,
    fee: float,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_history_fn: FeatureHistoryFn | None = None,
    fetch_regime: Callable[[str], ExternalFeatureBundle] | None = None,
) -> AccountRunResult:
    account_id = row_expect_int(account, "id")
    snapshot_time = utc_now_iso()
    audit = BookRunAudit()
    # Universes are book-owned and required (revision 0008): each book resolves
    # its own names; the global list is only the guard for malformed data.
    run_account_book_rotations(conn, account=account, decision_time=snapshot_time, fetch_regime=fetch_regime)
    intents = generate_book_trade_intents(
        conn,
        account=account,
        market=market,
        max_trades=max_trades,
        fee=fee,
        feature_history_fn=feature_history_fn,
        # Seeded per run date, so candidate order is stable within a run and
        # reproducible from the audit trail, but does not favour the same names
        # run after run.
        selection_seed=snapshot_time[:10],
    )
    if not intents:
        persist_book_run_audit(conn, account_id=account_id, snapshot_time=snapshot_time, audit=audit)
        return _account_run_result(account, audit)

    # Intents are book-keyed; the intent's book_id feeds the risk audit.
    book_intents: list[BookTradeIntent] = [
        BookTradeIntent(
            book_id=candidate.book_id,
            account_id=candidate.account_id,
            strategy_id=None,
            symbol=candidate.symbol,
            side=candidate.side,
            qty=float(candidate.qty),
            requested_price=float(candidate.requested_price),
        )
        for candidate in intents
    ]

    # Pre-flight: NAV-mark books, then run the equity reconciliation kill switch once
    # for the run (reconciliation is per-run, not
    # per-book). The batch gate then applies the notional caps + stale-price across all
    # books with reconcile=False, so cross-book exposure caps are enforced together.
    nav_results = mark_account_to_market(conn, account_id=account_id, prices=market.prices, as_of=snapshot_time)
    unpriced_symbols = sorted({symbol for result in nav_results for symbol in result.unpriced_symbols})
    if unpriced_symbols:
        # A held symbol with no live mark is carried at cost in book equity but
        # skipped by the equity snapshot, so reconcile_book_equity would report a
        # spurious reconciliation_mismatch. Hold the book on the real cause and
        # skip the now-uninformative equity check — a run must not trade a book it
        # cannot value. See docs/overview.md (Known limitations).
        reconciliation_reasons = [KILL_SWITCH_REASON_UNPRICED_POSITION]
    else:
        reconciliation_reasons = reconcile_book_equity(conn, account_id=account_id)
    gate = BookPreSubmitGate(
        prices=market.prices,
        snapshot_time=snapshot_time,
        reconcile=False,
        config=RiskGateConfig(symbol_sector_map=load_symbol_sector_map()),
    )
    gate_result = gate.evaluate(conn, account_id=account_id, intents=book_intents)

    audit.risk_decisions = _risk_decisions_from_gate(gate_result.decisions)
    audit.kill_switch_reasons = list(gate_result.kill_switch_reasons) + reconciliation_reasons
    for reason in audit.kill_switch_reasons:
        audit.record_block(reason)
    audit.blocked_count = len(gate_result.blocked_intents)
    audit.rescaled_count = len(gate_result.rescaled_intents)
    audit.allowed_count = sum(1 for d in gate_result.decisions if d.action == "allow")

    # A kill switch (stale-price or reconciliation) holds the whole run.
    approved_intents = [] if audit.kill_switch_reasons else gate_result.approved_intents
    if not approved_intents:
        persist_book_run_audit(conn, account_id=account_id, snapshot_time=snapshot_time, audit=audit)
        return _account_run_result(account, audit)

    approved_by_book: dict[int, list[BookTradeIntent]] = defaultdict(list)
    for book_intent in approved_intents:
        approved_by_book[book_intent.book_id].append(book_intent)

    broker = broker_factory(account)
    try:
        for book_id, book_intents_for_book in approved_by_book.items():
            result = submit_book_intents(
                conn,
                book_id=book_id,
                account_id=account_id,
                intents=book_intents_for_book,
                broker=broker,
                gate=AllowAllGate(),  # gating already ran once above for the whole batch
                fee=fee,
                # Checked before every order, not once per book.
                enforce_throttle=lambda: enforce_runtime_trade_throttles(conn, trade_time_iso=utc_now_iso()),
            )
            if result.throttled:
                # The throttle is global: no later book submits either.
                audit.record_block(RISK_REASON_TRADE_THROTTLE_EXCEEDED, book_id=book_id)
                audit.submitted_count += result.submitted_count
                break
            audit.submitted_count += result.submitted_count
            if KILL_SWITCH_REASON_BROKER_API_ANOMALY in result.kill_switch_reasons:
                audit.kill_switch_reasons.append(KILL_SWITCH_REASON_BROKER_API_ANOMALY)
                audit.record_block(KILL_SWITCH_REASON_BROKER_API_ANOMALY, book_id=book_id)
                break

        persist_book_run_audit(conn, account_id=account_id, snapshot_time=snapshot_time, audit=audit)
        return _account_run_result(account, audit)
    finally:
        broker.disconnect()


def run_for_account(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    market: MarketInputs,
    max_trades: int,
    fee: float,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
) -> AccountRunResult:
    """Run the account's trading books (the one execution path, ADR 014).

    Every active, openly assigned book — the default book included — trades
    through the book flow. Books without an open assignment do not trade.
    """
    now_iso = utc_now_iso()
    if not is_runtime_submission_window_open(now_iso):
        return AccountRunResult(account_name=account_name, submitted_count=0, submission_window_closed=True)
    feature_history_fn = build_feature_history_fn(feature_fetchers)
    account = get_account(conn, account_name)
    return _run_books_for_account(
        conn,
        account=account,
        market=market,
        max_trades=max_trades,
        fee=fee,
        broker_factory=broker_factory,
        feature_history_fn=feature_history_fn,
        fetch_regime=feature_fetchers.fetch_policy,
    )
