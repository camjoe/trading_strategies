"""Rotation strategy-metrics builder.

Builds a strategy's rotation metrics from the canonical evaluation artifact's
decision score. This is the per-strategy scoring core behind
``build_book_challenger_evaluations``, so every incumbent and challenger is
scored apples-to-apples through one source.
"""

from __future__ import annotations

import sqlite3

from trading.domain.evaluation_decision_score import derive_decision_score
from trading.models import AccountRecord
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics


def build_rotation_strategy_metrics(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    strategy_name: str,
) -> RotationStrategyMetrics:
    """Build rotation metrics for one strategy from the canonical evaluation artifact.

    Both the incumbent and each challenger are scored through the same source — the
    strategy evaluation artifact's decision score — so champion/challenger comparison
    is apples-to-apples. The multi-component ``RotationStrategyMetrics`` collapses onto
    the single blended decision score for now; the richer component decomposition is a
    later refinement.
    """
    # The one deliberate deferred import in the books/evaluation/accounts trio:
    # this call is the single back-edge (books -> evaluation) in an otherwise
    # one-directional import graph (evaluation/accounts/backtesting -> books).
    # Deferring it here lets every downstream consumer import books at module
    # level without a package-init cycle.
    from trading.services.evaluation import fetch_strategy_evaluation_for_account_row

    artifact = fetch_strategy_evaluation_for_account_row(conn, account, strategy_name=strategy_name)
    decision = derive_decision_score(artifact)
    comparable_score = decision.score if decision.score is not None else 0.0
    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        trade_count=artifact.backtest.trade_count or 0,
        risk_adjusted_return=comparable_score,
        stability=0.0,
        drawdown_penalty=0.0,
        cost_penalty=0.0,
        regime_fit=0.0,
    )
