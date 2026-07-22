"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import asdict

import pandas as pd

from common.coercion import row_expect_int
from common.time import parse_utc_iso
from common.time import utc_now_iso
from collections.abc import Callable, Mapping

from trading.models import AccountRecord
from trading.models.orders.broker_order import OrderFill
from trading.domain.broker_connection import BrokerConnection
from trading.domain.feature_provider import FeatureFetcherSet
from trading.domain.market_hours import is_regular_us_equity_market_open
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.services.accounts import get_account
from trading.services.operational_settings import enforce_runtime_trade_throttles
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.services.execution.selection.selection import (
    FeatureHistoryFn,
    build_feature_history_fn,
)
from trading.services.execution.open_order_reconciliation import (
    reconcile_open_orders_impl,
    resolve_reconciliation_exec_id,
)
from trading.services.market_data import MarketDataProvider
from trading.services.execution.risk import (
    persist_book_risk_snapshot,
    persist_normalized_risk_decisions,
)
from trading.models.execution.book_trade_candidate import BookTradeCandidate
from trading.models.execution.risk_gate_decision import RiskGateDecision
from trading.models.execution.risk_gate_config import RiskGateConfig
from trading.services.execution.selection.book_intents import generate_book_trade_intents
from trading.services.books.sector_config import load_symbol_sector_map
from trading.services.books.rotation.engine import (
    evaluate_and_apply_book_rotation,
    resolve_rotation_policy_config,
)
from trading.services.books.rotation.challenger_evaluation import build_book_challenger_evaluations
from trading.repositories.positions import PositionRepository
from trading.repositories.books import BookRepository
from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.services.execution.submission import submit_book_intents
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.pre_submit_gate import BookPreSubmitGate
from trading.services.execution.nav import mark_account_to_market
from trading.services.execution.reconciliation import reconcile_book_equity

logger = logging.getLogger(__name__)

# Kill-switch reason when required price marks are unavailable or invalid.
KILL_SWITCH_REASON_STALE_PRICE_DATA = "stale_price_data"
# Kill-switch reason when book/account equity reconciliation is out of tolerance.
KILL_SWITCH_REASON_RECONCILIATION_MISMATCH = "reconciliation_mismatch"
# Kill-switch reason when no account snapshot exists for reconciliation guard.
KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING = "reconciliation_snapshot_missing"
# Kill-switch reason when latest account snapshot is older than freshness threshold.
KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT = "stale_reconciliation_snapshot"
# Kill-switch reason when broker submission raises an exception.
KILL_SWITCH_REASON_BROKER_API_ANOMALY = "broker_api_anomaly"

# Maximum allowed age for account snapshot freshness validation (seconds).
MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS = 6 * 60 * 60

# Risk-decision reason when the global trade throttle blocks further submissions.
RISK_REASON_TRADE_THROTTLE_EXCEEDED = "trade_throttle_exceeded"


def _is_runtime_submission_window_open(now_iso: str) -> bool:
    return is_regular_us_equity_market_open(parse_utc_iso(now_iso))


def _resolve_reconciliation_exec_id(
    *,
    broker_order_id: str,
    fill: OrderFill,
    fill_index: int,
) -> str:
    return resolve_reconciliation_exec_id(
        broker_order_id=broker_order_id,
        fill=fill,
        fill_index=fill_index,
    )


def _persist_book_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
) -> None:
    # Exposure is sourced from the clean book positions/equity (the submission path's
    # source of truth); persisted to the account-keyed risk_snapshots table.
    persist_book_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        kill_switch_triggered=kill_switch_triggered,
        payload=payload,
        fetch_positions_for_account_fn=lambda c, *, account_id: PositionRepository(c).fetch_for_account(
            account_id=account_id
        ),
        fetch_books_for_account_fn=lambda c, *, account_id: BookRepository(c).fetch_for_account(account_id=account_id),
        insert_risk_snapshot_fn=RiskSnapshotRepository(conn).insert,
        symbol_sector_map=load_symbol_sector_map(),
    )


def _persist_normalized_risk_decisions(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    decision_time: str,
    risk_decisions: list[dict[str, object]],
) -> None:
    persist_normalized_risk_decisions(
        conn,
        account_id=account_id,
        decision_time=decision_time,
        risk_decisions=risk_decisions,
        insert_risk_decision_fn=lambda c, **kwargs: RiskDecisionRepository(c).insert(**kwargs),
    )


def _run_book_rotation_decisions(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    decision_time: str,
) -> None:
    # Scheduling is book-owned (ADR 014): the evaluation resolves each book's
    # enabled gate, challenger schedule, and lookback from its settings row.
    shadow_eval = build_book_challenger_evaluations(
        conn,
        account=account,
        as_of_iso=decision_time,
    )
    for book_eval in shadow_eval.books:
        # Per-book effective policy: book_rotation_settings overrides with
        # code-default fallback.
        config = resolve_rotation_policy_config(
            conn,
            book_id=book_eval.book_id,
            rolling_window_days=book_eval.rolling_window_days,
            config_version=f"book-rotation:{decision_time[:10]}",
        )
        evaluate_and_apply_book_rotation(
            conn,
            book_id=book_eval.book_id,
            incumbent=book_eval.incumbent,
            challengers=book_eval.challengers,
            config=config,
            decision_time=decision_time,
        )


def _risk_decisions_from_gate(decisions: list[RiskGateDecision]) -> list[dict[str, object]]:
    """Convert the gate's book-keyed decisions into audit dicts."""
    return [asdict(decision) for decision in decisions]


def _persist_book_run_audit(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    risk_decisions: list[dict[str, object]],
    kill_switch_reasons: list[str],
    summary: dict[str, object],
) -> None:
    _persist_normalized_risk_decisions(
        conn,
        account_id=account_id,
        decision_time=snapshot_time,
        risk_decisions=risk_decisions,
    )
    _persist_book_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        kill_switch_triggered=bool(kill_switch_reasons),
        payload={
            "kill_switch_reasons": kill_switch_reasons,
            "risk_decisions": risk_decisions,
            "summary": summary,
        },
    )


def _run_books_for_account(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    max_trades: int,
    fee: float,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> int:
    account_id = row_expect_int(account, "id")
    snapshot_time = utc_now_iso()
    # Universes are book-owned and required (revision 0008): each book resolves
    # its own names; the global list is only the guard for malformed data.
    _run_book_rotation_decisions(conn, account=account, decision_time=snapshot_time)
    intents = generate_book_trade_intents(
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
    if not intents:
        _persist_book_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=[],
            kill_switch_reasons=[],
            summary={"submitted_count": 0, "blocked_count": 0, "rescaled_count": 0, "allowed_count": 0},
        )
        return 0

    # Intents are book-keyed; keep the book → intent context for the audit
    # trail and fill notes (the intent's book_id feeds the risk audit).
    book_intents: list[BookTradeIntent] = []
    candidate_by_book: dict[int, BookTradeCandidate] = {}
    for candidate in intents:
        book_intents.append(
            BookTradeIntent(
                book_id=candidate.book_id,
                account_id=candidate.account_id,
                strategy_id=None,
                symbol=candidate.symbol,
                side=candidate.side,
                qty=float(candidate.qty),
                requested_price=float(candidate.requested_price),
            )
        )
        candidate_by_book[candidate.book_id] = candidate

    # Pre-flight: NAV-mark books, then run the equity reconciliation kill switch once
    # for the run (reconciliation is per-run, not
    # per-book). The batch gate then applies the notional caps + stale-price across all
    # books with reconcile=False, so cross-book exposure caps are enforced together.
    mark_account_to_market(conn, account_id=account_id, prices=prices, as_of=snapshot_time)
    reconciliation_reasons = reconcile_book_equity(conn, account_id=account_id, now_iso=snapshot_time)
    gate = BookPreSubmitGate(
        prices=prices,
        snapshot_time=snapshot_time,
        reconcile=False,
        config=RiskGateConfig(symbol_sector_map=load_symbol_sector_map()),
    )
    gate_result = gate.evaluate(conn, account_id=account_id, intents=book_intents)

    risk_decisions = _risk_decisions_from_gate(gate_result.decisions)
    kill_switch_reasons = list(gate_result.kill_switch_reasons) + reconciliation_reasons
    for reason in kill_switch_reasons:
        risk_decisions.append({"action": "block", "reason_code": reason})
    allowed_count = sum(1 for d in gate_result.decisions if d.action == "allow")
    summary_counts: dict[str, object] = {
        "blocked_count": len(gate_result.blocked_intents),
        "rescaled_count": len(gate_result.rescaled_intents),
        "allowed_count": allowed_count,
    }

    # A kill switch (stale-price or reconciliation) holds the whole run.
    approved_intents = [] if kill_switch_reasons else gate_result.approved_intents
    if not approved_intents:
        _persist_book_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=risk_decisions,
            kill_switch_reasons=kill_switch_reasons,
            summary={"submitted_count": 0, **summary_counts},
        )
        return 0

    approved_by_book: dict[int, list[BookTradeIntent]] = defaultdict(list)
    for book_intent in approved_intents:
        approved_by_book[book_intent.book_id].append(book_intent)

    broker = broker_factory(account)
    try:
        submitted_count = 0
        for book_id, book_intents_for_book in approved_by_book.items():
            candidate = candidate_by_book[book_id]

            # The global trade throttle (operational settings) applies across
            # the whole run: once exceeded, no further books submit.
            try:
                enforce_runtime_trade_throttles(conn, trade_time_iso=utc_now_iso())
            except RuntimeTradeThrottleExceededError:
                risk_decisions.append(
                    {
                        "action": "block",
                        "reason_code": RISK_REASON_TRADE_THROTTLE_EXCEEDED,
                        "book_id": candidate.book_id,
                    }
                )
                break

            result = submit_book_intents(
                conn,
                book_id=book_id,
                account_id=account_id,
                intents=book_intents_for_book,
                broker=broker,
                gate=AllowAllGate(),  # gating already ran once above for the whole batch
                fee=fee,
            )
            submitted_count += result.submitted_count
            if KILL_SWITCH_REASON_BROKER_API_ANOMALY in result.kill_switch_reasons:
                kill_switch_reasons.append(KILL_SWITCH_REASON_BROKER_API_ANOMALY)
                risk_decisions.append(
                    {
                        "action": "block",
                        "reason_code": KILL_SWITCH_REASON_BROKER_API_ANOMALY,
                        "book_id": candidate.book_id,
                    }
                )
                break

        _persist_book_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=risk_decisions,
            kill_switch_reasons=kill_switch_reasons,
            summary={"submitted_count": submitted_count, **summary_counts},
        )
        return submitted_count
    finally:
        broker.disconnect()


def run_for_account(
    conn: sqlite3.Connection,
    account_name: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    max_trades: int,
    fee: float,
    *,
    histories: Mapping[str, pd.Series] | None = None,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    provider: MarketDataProvider | None = None,
) -> int:
    """Run the account's trading books (the one execution path, ADR 014).

    Every active, openly assigned book — the default book included — trades
    through the book flow. Books without an open assignment do not trade.
    """
    now_iso = utc_now_iso()
    if not _is_runtime_submission_window_open(now_iso):
        return 0
    feature_history_fn = build_feature_history_fn(feature_fetchers)
    account = get_account(conn, account_name)
    return _run_books_for_account(
        conn,
        account_name=account_name,
        account=account,
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank_proxy,
        max_trades=max_trades,
        fee=fee,
        broker_factory=broker_factory,
        feature_fetchers=feature_fetchers,
        histories=histories,
        feature_history_fn=feature_history_fn,
    )


def reconcile_open_broker_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
    *,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
) -> int:
    """Poll the account broker for fill updates on all open persisted clean orders.

    For each open ``orders`` row the broker reports fills on, this function:
      - Inserts any new ``order_fills`` rows and applies them to the book
        (positions/ledger/balances via the shared ``apply_book_fill``)
      - Updates the ``orders`` row status/fill state

    Returns the number of orders that were newly FILLED in this call.
    ``account_name``/``fee`` are retained for call-site compatibility; fills
    carry their own costs and account history derives from the fill rows.

    Called periodically for accounts with broker-managed open orders. It is a no-op
    for paper accounts, which fill synchronously and report no open trades.
    """
    del account_name, fee
    return reconcile_open_orders_impl(
        conn,
        account,
        get_broker_for_account_fn=broker_factory,
    )


def reconcile_open_ib_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
    *,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
) -> int:
    """Compatibility alias for the old broker reconciliation name."""
    return reconcile_open_broker_orders(conn, account_name, account, fee, broker_factory=broker_factory)
