"""Operator-facing text for the advisor digest and decision ledger."""

from __future__ import annotations

from trading.domain.advisor import outcome_window_end
from trading.domain.advisor_scorecard import EDGE_INTERVAL_CONFIDENCE, MIN_DECISIONS_FOR_RANKING
from trading.models.advisor import (
    REGIMES,
    AdvisorAccountDigest,
    AdvisorBookDigest,
    AdvisorDigest,
    DecisionScoreResult,
    Scorecard,
    ScorecardGroup,
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


def _render_book(book: AdvisorBookDigest) -> list[str]:
    evidence = book.evidence
    walk_forward = evidence.walk_forward
    label = f"{book.book_name} (default)" if book.is_default else book.book_name
    since = f" since {book.assigned_since[:10]}" if book.assigned_since else ""
    lines = [
        f"-- book {label}: {book.strategy_key or 'no strategy assigned'}{since}",
        f"   Paper: return {_pct(evidence.paper_return_pct)} over {evidence.paper_snapshot_count} snapshots",
        f"   Walk-forward: mean OOS {_pct(walk_forward.average_return_pct)}, "
        f"worst {_pct(walk_forward.worst_return_pct)} over {len(walk_forward.window_returns)} windows",
        "   Flags:",
    ]
    lines.extend(f"   - {flag.code}: {flag.reason}" for flag in book.flags)
    if not book.flags:
        lines.append("   - none")
    lines.append("   Recent decisions:")
    lines.extend(f"   - {render_decision_line(record)}" for record in book.recent_decisions)
    if not book.recent_decisions:
        lines.append("   - none recorded")
    return lines


def _render_account(account: AdvisorAccountDigest) -> list[str]:
    lines = [f"== {account.account_name} == benchmark {account.benchmark_ticker}, {len(account.books)} book(s)"]
    for book in account.books:
        lines.extend(_render_book(book))
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


def _render_edge(group: ScorecardGroup) -> str:
    if not group.rankable:
        return f"insufficient decisions ({group.measured_count} of {MIN_DECISIONS_FOR_RANKING})"
    if group.mean_edge_pct is None or group.edge_interval is None:
        return "no measured edge"
    low, high = group.edge_interval
    return f"{group.mean_edge_pct:+.2f} pp ({low:+.2f}, {high:+.2f})"


def render_scorecard_lines(scorecard: Scorecard) -> list[str]:
    confidence = f"{EDGE_INTERVAL_CONFIDENCE:.0%}"
    lines = [
        f"Scorecard by {scorecard.group_by} (generated {scorecard.generated_at}) - "
        f"{scorecard.rankable_count} rankable; a leader needs a {confidence} interval wholly above the rest",
    ]
    if not scorecard.groups:
        lines.append("No scored decisions yet.")
        return lines
    edge_label = f"mean edge ({confidence} CI)"
    header = f"{'group':<30} {'scored':>6} {'scorable':>8} {'points':>6}  {edge_label:<34}"
    lines.append(header + "".join(f" {regime:>5}" for regime in REGIMES))
    for group in scorecard.groups:
        lines.append(
            f"{group.key[:30]:<30} {group.scored_count:>6} {group.scorable_rate:>8.0%} {group.points:>+6}  "
            f"{_render_edge(group):<34}" + "".join(f" {group.points_by_regime[regime]:>+5}" for regime in REGIMES)
        )
    if scorecard.leader is not None:
        lines.append(f"Leader: {scorecard.leader}")
    elif scorecard.rankable_count >= 2:
        lines.append("No leader: the rankable groups' intervals overlap, so they are not distinguishable.")
    return lines
