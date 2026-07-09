"""Rotation strategy-metrics builder (paradigm-neutral).

Builds a strategy's rotation metrics from the canonical evaluation artifact's
decision score. This is the shared per-strategy scoring core used by both candidate
enumerators — the book-keyed ``build_book_rotation_candidates`` (an account's default
book) and the sleeve ``build_book_challenger_evaluations`` (sleeve books) — so every
incumbent and challenger is scored apples-to-apples through one source.
"""

from __future__ import annotations

import sqlite3

from trading.domain.evaluation_decision_score import derive_decision_score
from trading.models import AccountRecord
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.services.evaluation import fetch_strategy_evaluation_for_account_row


def build_rotation_strategy_metrics(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    strategy_name: str,
    param_set_id: int | None,
) -> RotationStrategyMetrics:
    """Build rotation metrics for one strategy from the canonical evaluation artifact.

    Both the incumbent and each challenger are scored through the same source — the
    strategy evaluation artifact's decision score — so champion/challenger comparison
    is apples-to-apples. The multi-component ``RotationStrategyMetrics`` collapses onto
    the single blended decision score for now; the richer component decomposition is a
    later refinement.
    """
    artifact = fetch_strategy_evaluation_for_account_row(conn, account, strategy_name=strategy_name)
    decision = derive_decision_score(artifact)
    comparable_score = decision.score if decision.score is not None else 0.0
    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        trade_count=artifact.backtest.trade_count or 0,
        risk_adjusted_return=comparable_score,
        stability=0.0,
        drawdown_penalty=0.0,
        cost_penalty=0.0,
        regime_fit=0.0,
    )
