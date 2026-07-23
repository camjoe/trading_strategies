from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
    the default-parameter baseline over the same OOS interval."""

    window_index: int
    split: WalkForwardSplit
    candidate_count: int
    winner: CandidateResult
    winner_oos: RunOutcome
    baseline_oos: RunOutcome


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
    OOS, and holdout evidence are kept distinct and never blended."""

    strategy: str
    account_name: str
    objective_name: str
    default_params: dict[str, Any]
    windows: list[WindowSelection] = field(default_factory=list)
    holdout: HoldoutOutcome | None = None
