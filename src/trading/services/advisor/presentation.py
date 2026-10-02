"""Operator-facing text for the advisor digest and decision ledger."""

from __future__ import annotations

from trading.domain.advisor import outcome_window_end
from trading.models.advisor import (
    AdvisorAccountDigest,
    AdvisorDigest,
    DecisionScoreResult,
    StrategyDecisionRecord,
)

_MISSING = "n/a"


def _pct(value: float | None) -> str:
    return _MISSING if value is None else f"{value:.2f}%"


def render_decision_line(record: StrategyDecisionRecord) -> str:
    outcome = record.outcome
    verdict = outcome.outcome_verdict or outcome.outcome_status
    return (
        f"#{record.id} {record.created_at[:10]} {record.decision_type} by {record.decided_by} "
        f"[{verdict}, window ends {outcome_window_end(record).isoformat()}]: {record.rationale}"
    )


def _render_account(account: AdvisorAccountDigest) -> list[str]:
    evaluation = account.evaluation
    basic = evaluation.basic
    paper = evaluation.paper_live
    walk_forward = evaluation.walk_forward
    lines = [
        f"== {account.account_name} ==",
        f"Strategy: {basic.active_strategy or _MISSING} | benchmark {basic.benchmark_ticker or _MISSING} "
        f"| confidence {evaluation.confidence.overall_confidence:.2f}",
        f"Paper: return {_pct(paper.return_pct)} over {paper.snapshot_count or 0} snapshots",
        f"Walk-forward: mean OOS {_pct(walk_forward.average_return_pct)}, "
        f"worst {_pct(walk_forward.worst_return_pct)} over {len(walk_forward.window_returns)} windows",
        "Flags:",
    ]
    lines.extend(f"- {flag.code}: {flag.reason}" for flag in account.flags)
    if not account.flags:
        lines.append("- none")
    lines.append("Recent decisions:")
    lines.extend(f"- {render_decision_line(record)}" for record in account.recent_decisions)
    if not account.recent_decisions:
        lines.append("- none recorded")
    return lines


def render_advisor_digest_lines(digest: AdvisorDigest) -> list[str]:
    lines = [f"Advisor digest as of {digest.as_of_date} (generated {digest.generated_at})"]
    if not digest.accounts:
        lines.append("No accounts.")
    for account in digest.accounts:
        lines.append("")
        lines.extend(_render_account(account))
    return lines


def render_score_result_line(result: DecisionScoreResult) -> str:
    outcome = result.outcome
    head = f"#{result.strategy_decision_id} {result.account_name} {result.decision_type}"
    if outcome.outcome_verdict is None:
        return f"{head}: {outcome.outcome_status} ({outcome.outcome_note})"
    return (
        f"{head}: {outcome.outcome_verdict} | chosen {_pct(outcome.chosen_return_pct)} "
        f"vs rejected {_pct(outcome.alternative_return_pct)} over "
        f"{outcome.outcome_window_start}..{outcome.outcome_window_end} "
        f"| paper {_pct(outcome.realized_return_pct)}, benchmark {_pct(outcome.realized_benchmark_return_pct)} "
        f"({outcome.outcome_note})"
    )


def render_scoring_lines(results: list[DecisionScoreResult]) -> list[str]:
    if not results:
        return ["No decisions are due for scoring."]
    return [f"Scored {len(results)} decision(s):", *(f"- {render_score_result_line(result)}" for result in results)]
