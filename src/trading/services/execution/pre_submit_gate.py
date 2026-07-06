"""Book-generic pre-submit safety gate.

Composes the pre-submit kill switches (stale-price + reconciliation) with the
notional risk gate, so every book — a plain account's default book and a sleeve's
bridging book alike — inherits the same guards.

**Book-as-bucket.** ``book_id`` is the risk bucket. The notional risk-gate
*policy* (``trading.domain.sleeve_risk_gate.evaluate_sleeve_risk_gate``) is reused
**unchanged**; this module only adapts book intents / equity / positions into the
sleeve-shaped inputs the policy expects (a sleeve was always just "the bucket").
Reconciliation likewise rolls up book equity for the account. Kept free of any
``auto_trading``/``sleeves`` *service* dependency so ``auto_trading`` can call this
at the cutover without a cycle.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace

from trading.domain.sleeve_risk_gate import evaluate_sleeve_risk_gate as evaluate_sleeve_risk_gate_policy
from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.execution.gate_result import GateResult
from trading.models.sleeves.sleeve_position_record import SleevePositionRecord
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_STALE_PRICE_DATA,
    MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
    RECONCILIATION_EQUITY_TOLERANCE,
)
from trading.services.execution.gate import GateAuditSink
from trading.services.execution.reconciliation import reconcile_book_equity


class BookPreSubmitGate:
    """Concrete :class:`~trading.services.execution.gate.PreSubmitGate`.

    Constructed per run with the price marks and the run's ``snapshot_time`` (used
    both as the reconciliation "now" and as the audit stamp). ``config`` supplies
    the notional caps + sector map; if omitted the domain defaults apply. An
    optional ``audit_sink`` persists the risk decisions/reasons (wired at 2a-4).
    """

    def __init__(
        self,
        *,
        prices: Mapping[str, float],
        snapshot_time: str,
        config: SleeveRiskGateConfig | None = None,
        equity_tolerance: float = RECONCILIATION_EQUITY_TOLERANCE,
        max_snapshot_age_seconds: int = MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
        audit_sink: GateAuditSink | None = None,
    ) -> None:
        self._prices = prices
        self._snapshot_time = snapshot_time
        self._config = config if config is not None else SleeveRiskGateConfig()
        self._equity_tolerance = abs(float(equity_tolerance))
        self._max_snapshot_age_seconds = int(max_snapshot_age_seconds)
        self._audit_sink = audit_sink

    def evaluate(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: int,
        intents: Sequence[BookTradeIntent],
    ) -> GateResult:
        intent_list = list(intents)
        decisions, approved, blocked, rescaled = self._run_notional_gate(conn, account_id, intent_list)

        kill_switch_reasons: list[str] = []
        # Stale-price only matters for intents that survived the notional gate.
        if approved and self._stale_price_symbols(approved):
            kill_switch_reasons.append(KILL_SWITCH_REASON_STALE_PRICE_DATA)
        # Reconciliation always runs so its verdict is captured for the audit.
        kill_switch_reasons.extend(self._reconciliation_kill_switches(conn, account_id))

        if kill_switch_reasons:
            # Any kill switch holds the whole book: nothing is approved for submission.
            approved = []

        if self._audit_sink is not None:
            self._audit_sink.record(
                conn,
                account_id=account_id,
                snapshot_time=self._snapshot_time,
                decisions=decisions,
                kill_switch_reasons=kill_switch_reasons,
                kill_switch_triggered=bool(kill_switch_reasons),
            )

        return GateResult(
            approved_intents=approved,
            blocked_intents=blocked,
            rescaled_intents=rescaled,
            kill_switch_reasons=kill_switch_reasons,
        )

    # --- notional risk gate (book-as-bucket adapter) ------------------------

    def _run_notional_gate(
        self,
        conn: sqlite3.Connection,
        account_id: int,
        intents: list[BookTradeIntent],
    ) -> tuple[list, list[BookTradeIntent], list[BookTradeIntent], list[BookTradeIntent]]:
        books = BookRepository(conn).fetch_for_account(account_id=account_id)
        equity_by_book = {book.id: book.current_equity for book in books}
        positions = PositionRepository(conn).fetch_for_account(account_id=account_id)
        sleeve_positions = [
            SleevePositionRecord(
                sleeve_id=position.book_id,
                symbol=position.symbol,
                qty=position.qty,
                avg_cost=position.avg_cost,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                updated_at=position.updated_at,
            )
            for position in positions
        ]
        result = evaluate_sleeve_risk_gate_policy(
            intents=[self._as_bucket_intent(intent) for intent in intents],
            sleeve_equity_by_id=equity_by_book,
            positions=sleeve_positions,
            config=self._config,
        )

        # Decisions are 1:1 with the input intents, in order — map each back to its
        # BookTradeIntent, applying the rescaled qty where the gate trimmed it.
        approved: list[BookTradeIntent] = []
        blocked: list[BookTradeIntent] = []
        rescaled: list[BookTradeIntent] = []
        for original, decision in zip(intents, result.decisions):
            if decision.action == "block":
                blocked.append(original)
            elif decision.action == "rescale":
                adjusted = replace(original, qty=float(decision.approved_qty))
                approved.append(adjusted)
                rescaled.append(adjusted)
            else:  # allow
                approved.append(original)
        return list(result.decisions), approved, blocked, rescaled

    def _as_bucket_intent(self, intent: BookTradeIntent) -> SleeveTradeIntent:
        # book_id plays the sleeve_id "bucket" role; the policy only uses side,
        # symbol, qty, requested_price, and the bucket id from the intent.
        return SleeveTradeIntent(
            account_id=intent.account_id,
            sleeve_id=intent.book_id,
            strategy_name="",
            param_set_id=None,
            side=intent.side,
            symbol=intent.symbol,
            qty=int(intent.qty),
            requested_price=float(intent.requested_price or 0.0),
            forced_sell=None,
            delta_est=None,
            iv_est=None,
        )

    # --- stale-price kill switch --------------------------------------------

    def _stale_price_symbols(self, intents: Sequence[BookTradeIntent]) -> list[str]:
        return sorted(
            {
                intent.symbol
                for intent in intents
                if self._prices.get(intent.symbol) is None or float(self._prices[intent.symbol]) <= 0
            }
        )

    # --- reconciliation kill switches ---------------------------------------

    def _reconciliation_kill_switches(self, conn: sqlite3.Connection, account_id: int) -> list[str]:
        # Delegates to the reusable equity reconciliation. Book equity is assumed
        # NAV-marked (by the runtime, via nav.mark_account_to_market) before the gate runs.
        return reconcile_book_equity(
            conn,
            account_id=account_id,
            now_iso=self._snapshot_time,
            equity_tolerance=self._equity_tolerance,
            max_snapshot_age_seconds=self._max_snapshot_age_seconds,
        )
