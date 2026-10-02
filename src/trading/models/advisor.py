"""Advisor data contracts: the strategy_decisions ledger and the advisor digest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str
from trading.models.evaluation import StrategyEvaluationArtifact

# Allowed strategy_decisions.decision_type values. Mirrors the table's CHECK.
DECISION_TYPE_HOLD = "hold"
DECISION_TYPE_ADJUST_PARAMS = "adjust_params"
DECISION_TYPE_PROPOSE_VARIANT = "propose_variant"
DECISION_TYPE_REQUEST_PROMOTION = "request_promotion"
DECISION_TYPE_DISABLE_STRATEGY = "disable_strategy"
DECISION_TYPE_RUN_EXPERIMENT = "run_experiment"
DECISION_TYPES = (
    DECISION_TYPE_HOLD,
    DECISION_TYPE_ADJUST_PARAMS,
    DECISION_TYPE_PROPOSE_VARIANT,
    DECISION_TYPE_REQUEST_PROMOTION,
    DECISION_TYPE_DISABLE_STRATEGY,
    DECISION_TYPE_RUN_EXPERIMENT,
)

# Allowed strategy_decisions.outcome_status values. Mirrors the table's CHECK.
OUTCOME_STATUS_PENDING = "pending"
OUTCOME_STATUS_MEASURED = "measured"
OUTCOME_STATUS_INCONCLUSIVE = "inconclusive"

# Allowed strategy_decisions.outcome_verdict values. Mirrors the table's CHECK.
OUTCOME_VERDICT_HELPED = "helped"
OUTCOME_VERDICT_NEUTRAL = "neutral"
OUTCOME_VERDICT_HURT = "hurt"
OUTCOME_VERDICTS = (OUTCOME_VERDICT_HELPED, OUTCOME_VERDICT_NEUTRAL, OUTCOME_VERDICT_HURT)

# Trading days after a decision before its outcome is scored. Matches the column default.
DEFAULT_OUTCOME_WINDOW_DAYS = 21

# decided_by value for a decision written by the advisor agent rather than an operator.
DECIDED_BY_AGENT = "agent"
# decided_by value for a decision recorded by an operator.
DECIDED_BY_OPERATOR = "operator"


@dataclass(frozen=True, slots=True, kw_only=True)
class StrategyDecisionInsert:
    """The write-once strategy_decisions columns a caller supplies when recording a decision.

    Field names are the column names: `StrategyDecisionRepository` builds the INSERT from
    this class. These columns cannot change after insert (enforced by a table trigger).
    """

    account_id: int
    book_id: int | None = None
    strategy_id: int | None = None
    decision_type: str
    rationale: str
    evidence_json: str
    optimization_experiment_id: int | None = None
    promotion_review_id: int | None = None
    decided_by: str
    created_at: str
    outcome_window_days: int = DEFAULT_OUTCOME_WINDOW_DAYS


@dataclass(frozen=True, slots=True, kw_only=True)
class StrategyDecisionOutcome:
    """The strategy_decisions outcome columns — the only columns updated after insert.

    Field names are the column names: `StrategyDecisionRepository.update_outcome` builds
    its UPDATE from this class.
    """

    outcome_status: str
    outcome_window_start: str | None = None
    outcome_window_end: str | None = None
    realized_return_pct: float | None = None
    realized_benchmark_return_pct: float | None = None
    outcome_verdict: str | None = None
    outcome_note: str | None = None
    outcome_measured_at: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StrategyDecisionRecord(StrategyDecisionInsert):
    """Persisted strategy_decisions row: the decision, its id, and its outcome so far."""

    id: int
    outcome: StrategyDecisionOutcome

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> StrategyDecisionRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            book_id=row_int(values, "book_id"),
            strategy_id=row_int(values, "strategy_id"),
            decision_type=row_expect_str(values, "decision_type"),
            rationale=row_expect_str(values, "rationale"),
            evidence_json=row_expect_str(values, "evidence_json"),
            optimization_experiment_id=row_int(values, "optimization_experiment_id"),
            promotion_review_id=row_int(values, "promotion_review_id"),
            decided_by=row_expect_str(values, "decided_by"),
            created_at=row_expect_str(values, "created_at"),
            outcome_window_days=row_expect_int(values, "outcome_window_days"),
            outcome=StrategyDecisionOutcome(
                outcome_status=row_expect_str(values, "outcome_status"),
                outcome_window_start=row_str(values, "outcome_window_start"),
                outcome_window_end=row_str(values, "outcome_window_end"),
                realized_return_pct=row_float(values, "realized_return_pct"),
                realized_benchmark_return_pct=row_float(values, "realized_benchmark_return_pct"),
                outcome_verdict=row_str(values, "outcome_verdict"),
                outcome_note=row_str(values, "outcome_note"),
                outcome_measured_at=row_str(values, "outcome_measured_at"),
            ),
        )


# Advisor digest flag codes: prompts for review, never a chosen action.
FLAG_DECISIONS_DUE = "decisions_due_for_scoring"
FLAG_NO_WALK_FORWARD = "no_walk_forward_evidence"
FLAG_BACKTEST_STALE = "backtest_stale"
FLAG_NO_PAPER_EVIDENCE = "no_paper_evidence"
FLAG_PAPER_RETURN_NEGATIVE = "paper_return_negative"
FLAG_DATA_GAPS = "data_gaps"


@dataclass(frozen=True, slots=True)
class AdvisorFlag:
    """One review prompt raised by the digest: a code plus the fact behind it."""

    code: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvisorAccountDigest:
    """One account's review substrate: its evaluation, its ledger state, and the flags raised."""

    account_name: str
    evaluation: StrategyEvaluationArtifact
    recent_decisions: list[StrategyDecisionRecord]
    due_decisions: list[StrategyDecisionRecord]
    flags: list[AdvisorFlag]


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvisorDigest:
    """The advisor digest across accounts, as of one trading date."""

    generated_at: str
    as_of_date: str
    accounts: list[AdvisorAccountDigest]
