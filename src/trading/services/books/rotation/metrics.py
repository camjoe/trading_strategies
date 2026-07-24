"""Rotation strategy-metrics builder.

Builds a strategy's rotation metrics from the canonical evaluation artifact's
decision score. This is the per-strategy scoring core behind
``build_book_challenger_evaluations``, so every incumbent and challenger is
scored apples-to-apples through one source.
"""

from __future__ import annotations

import sqlite3

from trading.domain.evaluation.decision_score import derive_decision_score
from trading.domain.rotation.score_components import (
    NEUTRAL_COMPONENT,
    drawdown_penalty_from_max_drawdown,
    stability_from_window_returns,
)
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
    strategy evaluation artifact — so champion/challenger comparison is
    apples-to-apples. Every component is in percentage points (see
    ``domain/rotation/score_components``).

    Two components are deliberately left at ``NEUTRAL_COMPONENT`` because no honest
    input exists for them:

    - ``cost_penalty``: the backtest simulation already deducts per-trade fees, so
      ``total_return_pct`` — and therefore ``risk_adjusted_return`` and
      ``drawdown_penalty`` — are net of modeled costs. Adding a turnover-based
      penalty on top would double-count the same cost.
    - ``regime_fit``: the repository has no market-regime detector, and the
      regime→strategy mapping columns were dropped as dead in migration ``0014``.
      There is nothing to fit against.

    Their weights remain configurable, so tuning either currently has no effect.
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
    walk_forward = artifact.walk_forward
    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        trade_count=artifact.backtest.trade_count or 0,
        risk_adjusted_return=comparable_score,
        stability=stability_from_window_returns(
            best_return_pct=walk_forward.best_return_pct,
            worst_return_pct=walk_forward.worst_return_pct,
            window_count=len(walk_forward.run_ids),
        ),
        drawdown_penalty=drawdown_penalty_from_max_drawdown(artifact.backtest.max_drawdown_pct),
        cost_penalty=NEUTRAL_COMPONENT,
        regime_fit=NEUTRAL_COMPONENT,
    )
