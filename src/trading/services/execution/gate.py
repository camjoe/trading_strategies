from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Protocol

from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.execution.gate_result import GateResult
from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision


class PreSubmitGate(Protocol):
    """Pre-submit safety policy applied to a book's intents before anything is sent.

    Implementations compose the kill switches (stale price, reconciliation
    mismatch/staleness/missing) and the domain risk gate (allow / rescale / block).
    Injected into :func:`~trading.services.execution.submission.submit_book_intents`
    so every book inherits the same guards and each gate stays unit-testable. The
    concrete production gate is built in P4 phase 2a-2.
    """

    def evaluate(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: int,
        intents: Sequence[BookTradeIntent],
    ) -> GateResult: ...


class GateAuditSink(Protocol):
    """Sink for the gate's risk audit (decisions + kill-switch reasons).

    Injected so the concrete persistence (risk snapshot + normalized decisions
    through the existing repos) is wired at the account/sleeve cutover (2a-4)
    without the clean execution service depending on the ``auto_trading`` layer
    that will call it. ``decisions`` are the notional-gate outcomes; under the
    book-as-bucket model their ``sleeve_id`` field carries the ``book_id``.
    """

    def record(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: int,
        snapshot_time: str,
        decisions: Sequence[SleeveRiskDecision],
        kill_switch_reasons: Sequence[str],
        kill_switch_triggered: bool,
    ) -> None: ...


class AllowAllGate:
    """Pass-through gate that approves every intent unchanged.

    A neutral seam for tests and for baselining a book with no book-specific
    guards. Real safety composition lives in the production gate (phase 2a-2), not
    here — this must never be used to bypass a kill switch on a live path.
    """

    def evaluate(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: int,
        intents: Sequence[BookTradeIntent],
    ) -> GateResult:
        return GateResult(approved_intents=list(intents))
