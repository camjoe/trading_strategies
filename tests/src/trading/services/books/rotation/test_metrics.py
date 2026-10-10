from __future__ import annotations

import pytest

from tests.support.repositories import insert_repository_account
from trading.domain.feature_provider import POLICY_RISK_ON_SCORE, ExternalFeatureBundle
from trading.domain.rotation.score_components import NEUTRAL_COMPONENT, REGIME_FIT_MATCH_BONUS_PCT
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts.mutations import get_account
from trading.services.books.rotation.metrics import build_rotation_strategy_metrics

_FETCH_TARGET = "trading.services.evaluation.queries.fetch_strategy_evaluation_for_account_row"


def _artifact(
    *,
    blended_score: float | None,
    trade_count: int,
    available: bool = True,
    max_drawdown_pct: float | None = None,
    window_returns: list[float] | None = None,
) -> StrategyEvaluationArtifact:
    walk_forward = EvaluationWalkForwardEvidence()
    if window_returns is not None:
        walk_forward = EvaluationWalkForwardEvidence(
            available=True,
            window_returns=window_returns,
            best_return_pct=max(window_returns),
            worst_return_pct=min(window_returns),
        )
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(
            available=available,
            trade_count=trade_count,
            max_drawdown_pct=max_drawdown_pct,
        ),
        walk_forward=walk_forward,
        confidence=EvaluationConfidence(blended_score=blended_score, overall_confidence=0.3),
    )


def test_build_rotation_strategy_metrics_maps_decision_score(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_metrics_eval")
    assert account_id is not None
    account = get_account(conn, "acct_metrics_eval")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="meanrev",
    )

    assert metrics.strategy_name == "meanrev"
    assert metrics.trade_count == 18
    assert metrics.risk_adjusted_return == 4.5
    # No walk-forward or drawdown evidence in this artifact, so both stay neutral.
    assert metrics.stability == 0.0
    assert metrics.drawdown_penalty == 0.0


def test_build_rotation_strategy_metrics_defaults_missing_score(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_missing")
    account = get_account(conn, "acct_metrics_missing")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=None, trade_count=0, available=False),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="meanrev",
    )

    assert metrics.risk_adjusted_return == 0.0
    assert metrics.trade_count == 0


def test_build_rotation_strategy_metrics_derives_risk_components(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_components")
    account = get_account(conn, "acct_metrics_components")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(
            blended_score=4.5,
            trade_count=18,
            max_drawdown_pct=-12.0,
            window_returns=[1.0, 3.0, 5.0],
        ),
    )

    metrics = build_rotation_strategy_metrics(conn, account=account, strategy_name="meanrev")

    # Drawdown is stored negative but SUBTRACTED by the policy, so it must be a magnitude.
    assert metrics.drawdown_penalty == pytest.approx(12.0)
    # Stability is the negative standard deviation of the walk-forward window returns.
    assert metrics.stability == pytest.approx(-2.0)
    # No honest input exists for regime_fit without fetch_regime — see the builder docstring.
    assert metrics.regime_fit == 0.0


def test_build_rotation_strategy_metrics_ignores_single_window_stability(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_one_window")
    account = get_account(conn, "acct_metrics_one_window")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(
            blended_score=4.5,
            trade_count=18,
            window_returns=[5.0],
        ),
    )

    metrics = build_rotation_strategy_metrics(conn, account=account, strategy_name="meanrev")

    assert metrics.stability == 0.0


def _bundle(risk_on_score: float | None) -> ExternalFeatureBundle:
    if risk_on_score is None:
        return ExternalFeatureBundle.unavailable(source="test")
    return ExternalFeatureBundle(features={POLICY_RISK_ON_SCORE: risk_on_score}, available=True, source="test")


def test_build_rotation_strategy_metrics_computes_regime_fit_on_match(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_regime_match")
    account = get_account(conn, "acct_metrics_regime_match")
    StrategyRepository(conn).ensure_id_for_label(label="trend", now_iso="2026-07-26T00:00:00Z")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="trend",
        fetch_regime=lambda _ticker: _bundle(0.90),  # well above the risk-on threshold
    )

    assert metrics.regime_fit == REGIME_FIT_MATCH_BONUS_PCT


def test_build_rotation_strategy_metrics_regime_fit_neutral_on_mismatch(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_regime_mismatch")
    account = get_account(conn, "acct_metrics_regime_mismatch")
    StrategyRepository(conn).ensure_id_for_label(label="trend", now_iso="2026-07-26T00:00:00Z")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="trend",
        fetch_regime=lambda _ticker: _bundle(0.10),  # well below the risk-off threshold: risk-off, trend wants risk-on
    )

    assert metrics.regime_fit == NEUTRAL_COMPONENT


def test_build_rotation_strategy_metrics_regime_fit_neutral_when_unavailable(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_regime_unavailable")
    account = get_account(conn, "acct_metrics_regime_unavailable")
    StrategyRepository(conn).ensure_id_for_label(label="trend", now_iso="2026-07-26T00:00:00Z")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="trend",
        fetch_regime=lambda _ticker: _bundle(None),  # a failed/stale live fetch
    )

    assert metrics.regime_fit == NEUTRAL_COMPONENT


def test_build_rotation_strategy_metrics_regime_fit_neutral_for_unknown_strategy(conn, monkeypatch) -> None:
    # No catalog row exists for "meanrev" in this test — resolving its style
    # must degrade to neutral, not raise.
    insert_repository_account(conn, name="acct_metrics_regime_unknown")
    account = get_account(conn, "acct_metrics_regime_unknown")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="meanrev",
        fetch_regime=lambda _ticker: _bundle(0.90),
    )

    assert metrics.regime_fit == NEUTRAL_COMPONENT
