from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.execution.book_trade_intent import BookTradeIntent


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of a :class:`~trading.services.execution.gate.PreSubmitGate` evaluation.

    ``approved_intents`` is authoritative for submission — it already contains any
    rescaled intents at their adjusted quantity. ``blocked_intents`` and
    ``rescaled_intents`` are audit views (``rescaled_intents`` is a subset of the
    approved set). ``kill_switch_reasons`` carries any pre-submit halt reasons
    (stale price, reconciliation mismatch, etc.); a non-empty list means the whole
    book is held and nothing is submitted.
    """

    approved_intents: list[BookTradeIntent] = field(default_factory=list)
    blocked_intents: list[BookTradeIntent] = field(default_factory=list)
    rescaled_intents: list[BookTradeIntent] = field(default_factory=list)
    kill_switch_reasons: list[str] = field(default_factory=list)
