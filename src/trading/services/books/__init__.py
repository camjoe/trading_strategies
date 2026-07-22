"""Multi-book trading services package.

Public surface for book state (assignments, sector config, helpers). Rotation
and challenger shadow evaluation live in the ``rotation`` sub-package; book-keyed
intent generation lives in ``trading.services.execution.selection``.
"""

from __future__ import annotations

from trading.models.execution.risk_gate_decision import RiskGateDecision
from trading.models.execution.risk_gate_config import RiskGateConfig
from trading.models.execution.risk_gate_result import RiskGateResult
from trading.models.execution.book_trade_candidate import BookTradeCandidate

__all__ = [
    "BookTradeCandidate",
    "RiskGateDecision",
    "RiskGateConfig",
    "RiskGateResult",
]
