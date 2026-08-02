"""Rotation strategy-metrics builder.

Builds a strategy's rotation metrics from the canonical evaluation artifact's
decision score. This is the per-strategy scoring core behind
``build_book_challenger_evaluations``, so every incumbent and challenger is
scored apples-to-apples through one source.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from trading.domain.evaluation.decision_score import derive_decision_score
from trading.domain.feature_provider import POLICY_RISK_ON_SCORE, ExternalFeatureBundle
from trading.domain.rotation.score_components import (
    NEUTRAL_COMPONENT,
    drawdown_penalty_from_max_drawdown,
    regime_bucket_from_risk_on_score,
    regime_fit_from_style,
    stability_from_window_returns,
)
from trading.domain.strategies.registry import PRIMITIVE_CATALOG
from trading.models import AccountRecord
from trading.models.rotation import RotationStrategyMetrics
from trading.repositories.strategies import StrategyRepository


def _resolve_strategy_style(conn: sqlite3.Connection, strategy_name: str) -> str | None:
    """Look up the catalog strategy's primitive family, or ``None`` if unresolvable.

    Never raises — an unknown strategy/primitive degrades to no regime affinity
    rather than blocking metrics building.
    """
    record = StrategyRepository(conn).fetch_by_key(strategy_key=strategy_name)
    if record is None:
        return None
    primitive_spec = PRIMITIVE_CATALOG.get(record.primitive)
    return primitive_spec.style if primitive_spec is not None else None


def build_rotation_strategy_metrics(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    strategy_name: str,
    fetch_regime: Callable[[str], ExternalFeatureBundle] | None = None,
) -> RotationStrategyMetrics:
    """Build rotation metrics for one strategy from the canonical evaluation artifact.

    Both the incumbent and each challenger are scored through the same source — the
    strategy evaluation artifact — so champion/challenger comparison is
    apples-to-apples. Every component is in percentage points (see
    ``domain/rotation/score_components``).

    ``regime_fit`` computes a real value when ``fetch_regime`` is given — the
    live-regime, family-derived design in ``docs/adr/019-rotation-score-components.md``
    (bucket ``policy_risk_on_score`` via ``regime_bucket_from_risk_on_score``,
    compare against the strategy's primitive family). Callers that don't pass
    ``fetch_regime`` (or that get an unavailable bundle) get ``NEUTRAL_COMPONENT``,
    exactly as before this existed — a stale/unreachable regime read must never
    block or bias the decision.
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

    regime_fit = NEUTRAL_COMPONENT
    if fetch_regime is not None:
        bundle = fetch_regime(strategy_name)
        current_regime = regime_bucket_from_risk_on_score(bundle.get(POLICY_RISK_ON_SCORE))
        strategy_style = _resolve_strategy_style(conn, strategy_name)
        regime_fit = regime_fit_from_style(strategy_style=strategy_style, current_regime=current_regime)

    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        trade_count=artifact.backtest.trade_count or 0,
        risk_adjusted_return=comparable_score,
        stability=stability_from_window_returns(window_returns=walk_forward.window_returns),
        drawdown_penalty=drawdown_penalty_from_max_drawdown(artifact.backtest.max_drawdown_pct),
        regime_fit=regime_fit,
    )
