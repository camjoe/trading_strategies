"""Shared pure formatting helpers for operator-facing reporting output.

These helpers turn already-computed payloads into display strings. They perform
no I/O and no persistence; the console rendering that consumes them lives in the
sibling ``account`` and ``comparison`` modules.
"""

from __future__ import annotations

from trading.models.evaluation import StrategyEvaluationArtifact
from trading.services.evaluation import backtest_freshness_display_parts

# Compare output shows at most this many individual positions before truncating.
POSITION_SUMMARY_LIMIT = 5


def positions_summary_text(positions: dict[str, float]) -> tuple[int, str]:
    position_count = len(positions)
    if not positions:
        return position_count, "none"
    sorted_positions = sorted(positions.items(), key=lambda x: x[0])
    positions_text = ", ".join(f"{ticker}:{qty:.2f}" for ticker, qty in sorted_positions[:POSITION_SUMMARY_LIMIT])
    if len(sorted_positions) > POSITION_SUMMARY_LIMIT:
        positions_text += ", ..."
    return position_count, positions_text


def _format_percentage_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _format_backtest_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    if not evaluation.backtest.available:
        return "backtest=N/A"
    return (
        f"backtest={_format_percentage_or_na(evaluation.backtest.total_return_pct)} "
        f"({evaluation.backtest.trade_count or 0} trades)"
    )


def _format_paper_live_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    label = evaluation.paper_live.mode or "paper_live"
    if not evaluation.paper_live.available:
        return f"{label}=N/A"
    return (
        f"{label}={_format_percentage_or_na(evaluation.paper_live.return_pct)} "
        f"({evaluation.paper_live.snapshot_count or 0} snapshots)"
    )


def _format_backtest_freshness_summary(evaluation: StrategyEvaluationArtifact) -> str:
    parts = backtest_freshness_display_parts(evaluation.diagnostics.backtest_freshness)
    if parts is None:
        return "backtest_age=N/A"
    age_days, label = parts
    return f"backtest_age={age_days:.1f}d ({label})"


def evaluation_summary_line(
    evaluation: StrategyEvaluationArtifact,
    *,
    prefix: str,
) -> str:
    return (
        f"{prefix}{_format_backtest_evidence_summary(evaluation)} | "
        f"{_format_paper_live_evidence_summary(evaluation)} | "
        f"{_format_backtest_freshness_summary(evaluation)} | "
        f"blended_score={_format_percentage_or_na(evaluation.confidence.blended_score)} | "
        f"confidence={evaluation.confidence.overall_confidence:.2f}"
    )


__all__ = [
    "POSITION_SUMMARY_LIMIT",
    "evaluation_summary_line",
    "positions_summary_text",
]
