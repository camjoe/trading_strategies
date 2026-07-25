from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from common.coercion import (
    row_expect_float,
    row_expect_int,
    row_expect_str,
    row_float,
    row_int,
    row_str,
)

# Objective identifier persisted/reported with an optimization run. Versioned so a
# future objective (calmar_v2, sharpe_v1, …) is a new name, never a silent redefinition.
CALMAR_V1_OBJECTIVE = "calmar_v1"

# Default walk-forward window geometry (months). Rolling training policy: each test
# window is preceded by a fixed-length training interval; a final holdout is carved
# off the end and never used for training or selection.
DEFAULT_TRAIN_MONTHS = 12
DEFAULT_TEST_MONTHS = 1
DEFAULT_STEP_MONTHS = 1
DEFAULT_HOLDOUT_MONTHS = 6

# Upper bound on the grid's Cartesian product. A search space larger than this is
# rejected rather than silently truncated, so a run always evaluates every candidate.
DEFAULT_CANDIDATE_BUDGET = 256

# Indicator warm-up applied to every window backtest (~126 trading days). Comfortably
# covers the technical strategies' warm-up needs (max(30, slow_window) bars) so short
# out-of-sample windows are valid; raise it for grids with very large window params.
DEFAULT_WARMUP_MONTHS = 6


@dataclass(frozen=True)
class WalkForwardSplit:
    """One chronological train/test split. Training ends strictly before testing."""

    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass
class OptimizerConfig:
    """Inputs for one walk-forward optimization experiment over a single strategy."""

    account_name: str
    tickers_file: str
    universe_history_dir: str | None
    strategy: str
    # Bounded search space: param name -> discrete candidate values. Keys must be a
    # subset of the strategy's known parameter keys (validated before any run).
    search_space: dict[str, list[Any]]
    start: str | None
    end: str | None
    lookback_months: int | None
    slippage_bps: float
    fee_per_trade: float
    allow_approximate_leaps: bool
    train_months: int = DEFAULT_TRAIN_MONTHS
    test_months: int = DEFAULT_TEST_MONTHS
    step_months: int = DEFAULT_STEP_MONTHS
    holdout_months: int = DEFAULT_HOLDOUT_MONTHS
    candidate_budget: int = DEFAULT_CANDIDATE_BUDGET
    warmup_months: int = DEFAULT_WARMUP_MONTHS
    objective_name: str = CALMAR_V1_OBJECTIVE


@dataclass(frozen=True)
class CandidateResult:
    """A single parameter set evaluated on one training interval."""

    index: int
    params: dict[str, Any]
    annualized_return_pct: float | None
    max_drawdown_pct: float
    trade_count: int
    score: float | None
    eligible: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class RunOutcome:
    """Persisted-run summary used for OOS/holdout reporting (evidence, not training)."""

    run_id: int
    total_return_pct: float
    annualized_return_pct: float | None
    max_drawdown_pct: float
    calmar_ratio: float | None
    trade_count: int
    benchmark_return_pct: float | None


@dataclass(frozen=True)
class WindowSelection:
    """The winner chosen on a window's training interval, plus its OOS evidence and
    the default-parameter baseline over the same OOS interval.

    ``candidates`` holds every evaluated candidate for the window (the winner among
    them), so the full attempted search — not just the winner — can be persisted as
    the per-window multiple-testing audit record."""

    window_index: int
    split: WalkForwardSplit
    candidate_count: int
    winner: CandidateResult
    winner_oos: RunOutcome
    baseline_oos: RunOutcome
    candidates: list[CandidateResult] = field(default_factory=list)


@dataclass(frozen=True)
class HoldoutOutcome:
    """The forward-carried winner's parameters run once over the untouched holdout,
    beside the default-parameter baseline over the same interval."""

    holdout_start: date
    holdout_end: date
    winner_params: dict[str, Any]
    winner: RunOutcome
    baseline: RunOutcome


@dataclass(frozen=True)
class OptimizationSummary:
    """Full result of one optimization experiment: per-window selections, holdout
    evidence, and the strategy's default params for side-by-side comparison. Training,
    OOS, and holdout evidence are kept distinct and never blended.

    ``experiment_id`` is the persisted ``optimization_experiments`` row id — the handle
    a later promotion (``backtest-optimize-promote``) resolves the winner from."""

    strategy: str
    account_name: str
    objective_name: str
    default_params: dict[str, Any]
    windows: list[WindowSelection] = field(default_factory=list)
    holdout: HoldoutOutcome | None = None
    experiment_id: int | None = None


@dataclass(frozen=True)
class OptimizationExperimentInsert:
    """Tier-1 persistence payload for one ``backtest-optimize`` run.

    Carries the run config, the forward-carried winner (the promotion candidate),
    a small OOS aggregate, and the untouched-holdout summary. Baseline numbers are
    summarized here because the optimizer runs the default-parameter baseline
    metrics-only (it is never persisted as a ``backtest_runs`` row)."""

    account_id: int
    strategy_id: int | None
    primitive: str
    objective_name: str
    search_space_json: str
    candidate_budget: int
    train_months: int
    test_months: int
    step_months: int
    holdout_months: int
    warmup_months: int
    start_date: str
    end_date: str
    window_count: int
    winner_params_json: str
    oos_mean_winner_return_pct: float | None
    oos_mean_baseline_return_pct: float | None
    oos_windows_beat_baseline: int | None
    holdout_run_id: int | None
    holdout_winner_return_pct: float | None
    holdout_baseline_return_pct: float | None


@dataclass(frozen=True)
class OptimizationExperimentRecord:
    """Persisted ``optimization_experiments`` row (read model).

    ``promoted_strategy_id`` is the audit link to the tradeable variant minted from
    ``winner_params_json``; ``None`` until the experiment is promoted."""

    id: int
    account_id: int
    strategy_id: int | None
    primitive: str
    objective_name: str
    search_space_json: str
    candidate_budget: int
    train_months: int
    test_months: int
    step_months: int
    holdout_months: int
    warmup_months: int
    start_date: str
    end_date: str
    window_count: int
    winner_params_json: str
    oos_mean_winner_return_pct: float | None
    oos_mean_baseline_return_pct: float | None
    oos_windows_beat_baseline: int | None
    holdout_run_id: int | None
    holdout_winner_return_pct: float | None
    holdout_baseline_return_pct: float | None
    promoted_strategy_id: int | None
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> OptimizationExperimentRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            strategy_id=row_int(values, "strategy_id"),
            primitive=row_expect_str(values, "primitive"),
            objective_name=row_expect_str(values, "objective_name"),
            search_space_json=row_expect_str(values, "search_space_json"),
            candidate_budget=row_expect_int(values, "candidate_budget"),
            train_months=row_expect_int(values, "train_months"),
            test_months=row_expect_int(values, "test_months"),
            step_months=row_expect_int(values, "step_months"),
            holdout_months=row_expect_int(values, "holdout_months"),
            warmup_months=row_expect_int(values, "warmup_months"),
            start_date=row_expect_str(values, "start_date"),
            end_date=row_expect_str(values, "end_date"),
            window_count=row_expect_int(values, "window_count"),
            winner_params_json=row_expect_str(values, "winner_params_json"),
            oos_mean_winner_return_pct=row_float(values, "oos_mean_winner_return_pct"),
            oos_mean_baseline_return_pct=row_float(values, "oos_mean_baseline_return_pct"),
            oos_windows_beat_baseline=row_int(values, "oos_windows_beat_baseline"),
            holdout_run_id=row_int(values, "holdout_run_id"),
            holdout_winner_return_pct=row_float(values, "holdout_winner_return_pct"),
            holdout_baseline_return_pct=row_float(values, "holdout_baseline_return_pct"),
            promoted_strategy_id=row_int(values, "promoted_strategy_id"),
            created_at=row_expect_str(values, "created_at"),
        )


@dataclass(frozen=True)
class OptimizationWindowInsert:
    """Persistence payload for one ``optimization_windows`` row.

    Records a window's train/test boundaries and links its persisted winner OOS
    ``backtest_runs`` row via ``oos_run_id`` — OOS metrics are read from that run,
    never copied here."""

    experiment_id: int
    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    oos_run_id: int


@dataclass(frozen=True)
class OptimizationWindowRecord:
    """Persisted ``optimization_windows`` row (read model)."""

    id: int
    experiment_id: int
    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    oos_run_id: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> OptimizationWindowRecord:
        return cls(
            id=row_expect_int(values, "id"),
            experiment_id=row_expect_int(values, "experiment_id"),
            window_index=row_expect_int(values, "window_index"),
            train_start=row_expect_str(values, "train_start"),
            train_end=row_expect_str(values, "train_end"),
            test_start=row_expect_str(values, "test_start"),
            test_end=row_expect_str(values, "test_end"),
            oos_run_id=row_expect_int(values, "oos_run_id"),
        )


@dataclass(frozen=True)
class OptimizationTrialInsert:
    """Persistence payload for one ``optimization_trials`` row.

    One evaluated grid candidate on a window's training interval — the
    multiple-testing audit record. Training candidates are metrics-only (never a
    ``backtest_runs`` row), so the objective value and its components are stored
    here directly. ``selected`` marks the window's forward-carried winner."""

    window_id: int
    candidate_index: int
    params_json: str
    params_hash: str
    objective_value: float | None
    annualized_return_pct: float | None
    max_drawdown_pct: float
    trade_count: int
    eligible: bool
    rejection_reason: str | None
    selected: bool


@dataclass(frozen=True)
class OptimizationTrialRecord:
    """Persisted ``optimization_trials`` row (read model)."""

    id: int
    window_id: int
    candidate_index: int
    params_json: str
    params_hash: str
    objective_value: float | None
    annualized_return_pct: float | None
    max_drawdown_pct: float
    trade_count: int
    eligible: bool
    rejection_reason: str | None
    selected: bool

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> OptimizationTrialRecord:
        return cls(
            id=row_expect_int(values, "id"),
            window_id=row_expect_int(values, "window_id"),
            candidate_index=row_expect_int(values, "candidate_index"),
            params_json=row_expect_str(values, "params_json"),
            params_hash=row_expect_str(values, "params_hash"),
            objective_value=row_float(values, "objective_value"),
            annualized_return_pct=row_float(values, "annualized_return_pct"),
            max_drawdown_pct=row_expect_float(values, "max_drawdown_pct"),
            trade_count=row_expect_int(values, "trade_count"),
            eligible=bool(row_expect_int(values, "eligible")),
            rejection_reason=row_str(values, "rejection_reason"),
            selected=bool(row_expect_int(values, "selected")),
        )
