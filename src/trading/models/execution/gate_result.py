from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of a :class:`~trading.services.execution.gate.PreSubmitGate` evaluation.

    ``approved_intents`` is authoritative for submission — it already contains any
    rescaled intents at their adjusted quantity. ``blocked_intents`` and
    ``rescaled_intents`` are audit views (``rescaled_intents`` is a subset of the
    approved set). ``kill_switch_reasons`` carries any pre-submit halt reasons
    (stale price, reconciliation mismatch, etc.); a non-empty list means the whole
    book is held and nothing is submitted. ``decisions`` are the notional-gate's
    per-intent outcomes (allow/rescale/block + reason codes), bucketed by book;
    callers use them to persist the risk audit. (``SleeveRiskDecision`` is the
    reused decision contract — its ``sleeve_id`` field carries the ``book_id``
    under the book-as-bucket model; P5 renames it.)
    """

    approved_intents: list[BookTradeIntent] = field(default_factory=list)
    blocked_intents: list[BookTradeIntent] = field(default_factory=list)
    rescaled_intents: list[BookTradeIntent] = field(default_factory=list)
    kill_switch_reasons: list[str] = field(default_factory=list)
    decisions: list[SleeveRiskDecision] = field(default_factory=list)
