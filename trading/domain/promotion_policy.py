from __future__ import annotations

from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.domain.promotion_models import (
    PROMOTION_STAGE_CANDIDATE,
    PROMOTION_STAGE_LIVE_ACTIVE,
    PROMOTION_STAGE_PAPER_OBSERVING,
    PROMOTION_STAGE_PROMOTION_REVIEW,
    PROMOTION_STAGE_RESEARCH_VALIDATED,
    PROMOTION_STATUS_BLOCKED,
    PROMOTION_STATUS_LIVE,
    PROMOTION_STATUS_OBSERVING,
    PROMOTION_STATUS_READY_FOR_REVIEW,
    PromotionAssessment,
)

# Research validation expects at least a small sample of backtest decisions.
MIN_RESEARCH_BACKTEST_TRADE_COUNT = 10

# Research validation expects enough backtest equity points to inspect curve shape.
MIN_RESEARCH_BACKTEST_SNAPSHOT_COUNT = 20

# Research validation requires a non-negative backtest return before paper observation.
MIN_RESEARCH_BACKTEST_RETURN_PCT = 0.0

# Research validation rejects backtests with drawdowns worse than this floor.
MIN_RESEARCH_MAX_DRAWDOWN_PCT = -25.0

# Grouped walk-forward evidence must also show a non-negative average return.
MIN_RESEARCH_WALK_FORWARD_AVERAGE_RETURN_PCT = 0.0

# Live-readiness review expects a modest amount of persisted paper observation.
MIN_LIVE_PAPER_SNAPSHOT_COUNT = 10

# Promotion review requires moderate blended confidence from the evaluation artifact.
MIN_LIVE_OVERALL_CONFIDENCE = 0.60

RESEARCH_EVIDENCE_REQUIRED = "Backtest evidence is required for promotion assessment."
GROUPED_WALK_FORWARD_REQUIRED = "Grouped walk-forward evidence is required for research validation."
PAPER_EVIDENCE_REQUIRED = "Paper evidence is required before manual promotion review."
ROTATION_ISOLATION_REQUIRED = (
    "Rotating accounts require strategy-isolated paper evidence before manual promotion review."
)
PAPER_ISOLATION_REQUIRED = "Paper evidence must be strategy-isolated before manual promotion review."
RESEARCH_NEXT_ACTION = "Produce research evidence that meets promotion thresholds."
PAPER_EVIDENCE_NEXT_ACTION = "Collect paper evidence before requesting manual promotion review."
PAPER_OBSERVATION_NEXT_ACTION = (
    "Continue paper observation until live-readiness blockers clear, then request manual promotion review."
)
PROMOTION_REVIEW_NEXT_ACTION = (
    "Automated checks passed. A human operator may review the evidence and manually enable live trading."
)
LIVE_ACTIVE_NEXT_ACTION = (
    "Live trading is already enabled. Continue manual oversight; automated live activation remains disabled."
)
LIVE_ALREADY_ENABLED_WARNING = (
    "Live trading is already enabled. This workflow remains read-only and will not change live status."
)
ROTATION_MANUAL_WARNING = (
    "Rotating accounts remain manual-only for final promotion, even when automated checks pass."
)
BACKTEST_WARNING_PREFIX = "Backtest warnings: "


def _append_threshold_blocker(
    blockers: list[str],
    *,
    value: float | int | None,
    minimum: float | int,
    message: str,
) -> None:
    if value is None or value < minimum:
        blockers.append(message)


def _research_blockers(artifact: StrategyEvaluationArtifact) -> list[str]:
    blockers: list[str] = []
    backtest = artifact.backtest
    walk_forward = artifact.walk_forward
    if not backtest.available:
        blockers.append(RESEARCH_EVIDENCE_REQUIRED)
        return blockers

    if not walk_forward.available or not walk_forward.grouped:
        blockers.append(GROUPED_WALK_FORWARD_REQUIRED)

    _append_threshold_blocker(
        blockers,
        value=backtest.trade_count,
        minimum=MIN_RESEARCH_BACKTEST_TRADE_COUNT,
        message=(
            "Backtest trade count must be at least "
            f"{MIN_RESEARCH_BACKTEST_TRADE_COUNT} for research validation."
        ),
    )
    _append_threshold_blocker(
        blockers,
        value=backtest.snapshot_count,
        minimum=MIN_RESEARCH_BACKTEST_SNAPSHOT_COUNT,
        message=(
            "Backtest snapshot count must be at least "
            f"{MIN_RESEARCH_BACKTEST_SNAPSHOT_COUNT} for research validation."
        ),
    )
    _append_threshold_blocker(
        blockers,
        value=backtest.total_return_pct,
        minimum=MIN_RESEARCH_BACKTEST_RETURN_PCT,
        message=(
            "Backtest return must be at least "
            f"{MIN_RESEARCH_BACKTEST_RETURN_PCT:.2f}% for research validation."
        ),
    )
    if (
        backtest.max_drawdown_pct is None
        or backtest.max_drawdown_pct < MIN_RESEARCH_MAX_DRAWDOWN_PCT
    ):
        blockers.append(
            "Backtest max drawdown must be no worse than "
            f"{MIN_RESEARCH_MAX_DRAWDOWN_PCT:.2f}% for research validation."
        )
    _append_threshold_blocker(
        blockers,
        value=walk_forward.average_return_pct,
        minimum=MIN_RESEARCH_WALK_FORWARD_AVERAGE_RETURN_PCT,
        message=(
            "Walk-forward average return must be at least "
            f"{MIN_RESEARCH_WALK_FORWARD_AVERAGE_RETURN_PCT:.2f}% for research validation."
        ),
    )
    return blockers


def _live_readiness_blockers(artifact: StrategyEvaluationArtifact) -> list[str]:
    blockers: list[str] = []
    paper_live = artifact.paper_live
    if not paper_live.available:
        blockers.append(PAPER_EVIDENCE_REQUIRED)
    if artifact.basic.rotation_enabled and not paper_live.strategy_isolated:
        blockers.append(ROTATION_ISOLATION_REQUIRED)
    elif paper_live.available and not paper_live.strategy_isolated:
        blockers.append(PAPER_ISOLATION_REQUIRED)

    if paper_live.available:
        _append_threshold_blocker(
            blockers,
            value=paper_live.snapshot_count,
            minimum=MIN_LIVE_PAPER_SNAPSHOT_COUNT,
            message=(
                "Paper snapshot count must be at least "
                f"{MIN_LIVE_PAPER_SNAPSHOT_COUNT} before manual promotion review."
            ),
        )
    _append_threshold_blocker(
        blockers,
        value=artifact.confidence.overall_confidence,
        minimum=MIN_LIVE_OVERALL_CONFIDENCE,
        message=(
            "Overall confidence must be at least "
            f"{MIN_LIVE_OVERALL_CONFIDENCE:.2f} before manual promotion review."
        ),
    )
    if artifact.diagnostics.data_gaps:
        blockers.append(
            "Required evaluation data gaps must be resolved: "
            + ", ".join(artifact.diagnostics.data_gaps)
        )
    return blockers


def _warnings(artifact: StrategyEvaluationArtifact) -> list[str]:
    warnings: list[str] = []
    if artifact.backtest.warnings:
        warnings.append(f"{BACKTEST_WARNING_PREFIX}{artifact.backtest.warnings}")
    if artifact.basic.rotation_enabled:
        warnings.append(ROTATION_MANUAL_WARNING)
    return warnings


def assess_promotion_readiness(artifact: StrategyEvaluationArtifact) -> PromotionAssessment:
    warnings = _warnings(artifact)
    if artifact.basic.live_trading_enabled:
        return PromotionAssessment(
            account_name=artifact.basic.account_name,
            strategy_name=artifact.basic.requested_strategy,
            evaluation_generated_at=artifact.meta.generated_at,
            stage=PROMOTION_STAGE_LIVE_ACTIVE,
            status=PROMOTION_STATUS_LIVE,
            ready_for_live=False,
            live_trading_enabled=True,
            overall_confidence=artifact.confidence.overall_confidence,
            data_gaps=list(artifact.diagnostics.data_gaps),
            blockers=[],
            warnings=[*warnings, LIVE_ALREADY_ENABLED_WARNING],
            next_action=LIVE_ACTIVE_NEXT_ACTION,
        )

    research_blockers = _research_blockers(artifact)
    if research_blockers:
        return PromotionAssessment(
            account_name=artifact.basic.account_name,
            strategy_name=artifact.basic.requested_strategy,
            evaluation_generated_at=artifact.meta.generated_at,
            stage=PROMOTION_STAGE_CANDIDATE,
            status=PROMOTION_STATUS_BLOCKED,
            ready_for_live=False,
            live_trading_enabled=False,
            overall_confidence=artifact.confidence.overall_confidence,
            data_gaps=list(artifact.diagnostics.data_gaps),
            blockers=research_blockers,
            warnings=warnings,
            next_action=RESEARCH_NEXT_ACTION,
        )

    live_blockers = _live_readiness_blockers(artifact)
    if not live_blockers:
        return PromotionAssessment(
            account_name=artifact.basic.account_name,
            strategy_name=artifact.basic.requested_strategy,
            evaluation_generated_at=artifact.meta.generated_at,
            stage=PROMOTION_STAGE_PROMOTION_REVIEW,
            status=PROMOTION_STATUS_READY_FOR_REVIEW,
            ready_for_live=True,
            live_trading_enabled=False,
            overall_confidence=artifact.confidence.overall_confidence,
            data_gaps=list(artifact.diagnostics.data_gaps),
            blockers=[],
            warnings=warnings,
            next_action=PROMOTION_REVIEW_NEXT_ACTION,
        )

    has_paper_evidence = artifact.paper_live.available
    return PromotionAssessment(
        account_name=artifact.basic.account_name,
        strategy_name=artifact.basic.requested_strategy,
        evaluation_generated_at=artifact.meta.generated_at,
        stage=(
            PROMOTION_STAGE_PAPER_OBSERVING
            if has_paper_evidence
            else PROMOTION_STAGE_RESEARCH_VALIDATED
        ),
        status=PROMOTION_STATUS_OBSERVING,
        ready_for_live=False,
        live_trading_enabled=False,
        overall_confidence=artifact.confidence.overall_confidence,
        data_gaps=list(artifact.diagnostics.data_gaps),
        blockers=live_blockers,
        warnings=warnings,
        next_action=(
            PAPER_OBSERVATION_NEXT_ACTION
            if has_paper_evidence
            else PAPER_EVIDENCE_NEXT_ACTION
        ),
    )
