"""Evaluation artifact data contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Current schema label for the first canonical evaluation artifact slice.
EVALUATION_ARTIFACT_VERSION = "phase2.v1"

# The initial assembler only reads persisted evidence already stored in SQLite.
EVALUATION_SOURCE_MODE = "persisted_only"


# --- Scope and metadata ---


@dataclass(frozen=True)
class EvaluationMeta:
    artifact_version: str = EVALUATION_ARTIFACT_VERSION
    source_mode: str = EVALUATION_SOURCE_MODE
    generated_at: str | None = None


@dataclass(frozen=True)
class EvaluationBasicScope:
    account_id: int | None = None
    account_name: str | None = None
    descriptive_name: str | None = None
    requested_strategy: str | None = None
    active_strategy: str | None = None
    benchmark_ticker: str | None = None
    instrument_mode: str | None = None
    rotation_enabled: bool = False
    live_trading_enabled: bool = False


# --- Evidence ---


@dataclass(frozen=True)
class BacktestFreshness:
    """Advisory staleness of a strategy's newest backtest evidence.

    ``age_days`` is the fractional age of the backtest run against the
    evaluation's generation time; ``is_stale`` compares it to
    ``stale_threshold_days``. ``available`` is False when there is no backtest
    run to measure. Advisory only — never affects confidence or decisions.
    """

    available: bool = False
    age_days: float | None = None
    stale_threshold_days: int = 0
    is_stale: bool = False


@dataclass(frozen=True)
class EvaluationBacktestEvidence:
    available: bool = False
    run_id: int | None = None
    run_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    created_at: str | None = None
    trade_count: int | None = None
    snapshot_count: int | None = None
    starting_equity: float | None = None
    ending_equity: float | None = None
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    warnings: str | None = None


@dataclass(frozen=True)
class EvaluationPaperLiveEvidence:
    available: bool = False
    mode: str | None = None
    source_level: str | None = None
    strategy_isolated: bool = False
    latest_snapshot_time: str | None = None
    snapshot_count: int | None = None
    starting_equity: float | None = None
    latest_equity: float | None = None
    return_pct: float | None = None
    cash: float | None = None
    market_value: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    # Bounds of the strategy's most recent live window (book snapshots sliced at
    # rotation_decisions boundaries).
    window_started_at: str | None = None
    window_ended_at: str | None = None


@dataclass(frozen=True)
class EvaluationWalkForwardEvidence:
    """Out-of-sample window record from a walk-forward optimization experiment.

    ``window_returns`` carries each window's OOS return in chronological order —
    the full distribution, not just its summary statistics — so consumers can
    measure dispersion directly instead of inferring it from the range.
    """

    available: bool = False
    window_returns: list[float] = field(default_factory=list)
    average_return_pct: float | None = None
    median_return_pct: float | None = None
    best_return_pct: float | None = None
    worst_return_pct: float | None = None


# --- Scoring ---


@dataclass(frozen=True)
class EvaluationConfidence:
    backtest_confidence: float = 0.0
    paper_live_confidence: float = 0.0
    overall_confidence: float = 0.0
    blended_score: float | None = None


@dataclass(frozen=True)
class EvaluationDecisionScore:
    """Decision-ready view of a strategy evaluation.

    A keyless value object derived from ``StrategyEvaluationArtifact`` so that
    compare, promotion, and rotation can consume one comparable score/confidence
    contract instead of reading evaluation confidence fields directly. It carries
    no account/strategy identity so a caller can produce one per candidate
    (e.g. per rotation challenger).

    ``score`` mirrors the artifact's confidence-weighted blended score and is
    ``None`` when no evidence contributes; ``has_evidence`` makes that fallback
    explicit so consumers never treat a missing score as ``0``.
    """

    score: float | None = None
    confidence: float = 0.0
    backtest_confidence: float = 0.0
    paper_live_confidence: float = 0.0
    has_evidence: bool = False
    data_gaps: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvaluationDiagnostics:
    data_gaps: list[str] = field(default_factory=list)
    # Advisory backtest staleness; None on artifacts built before the freshness diagnostic existed.
    backtest_freshness: BacktestFreshness | None = None


# --- The artifact ---


@dataclass(frozen=True)
class StrategyEvaluationArtifact:
    meta: EvaluationMeta = field(default_factory=EvaluationMeta)
    basic: EvaluationBasicScope = field(default_factory=EvaluationBasicScope)
    backtest: EvaluationBacktestEvidence = field(default_factory=EvaluationBacktestEvidence)
    walk_forward: EvaluationWalkForwardEvidence = field(default_factory=EvaluationWalkForwardEvidence)
    paper_live: EvaluationPaperLiveEvidence = field(default_factory=EvaluationPaperLiveEvidence)
    confidence: EvaluationConfidence = field(default_factory=EvaluationConfidence)
    diagnostics: EvaluationDiagnostics = field(default_factory=EvaluationDiagnostics)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
