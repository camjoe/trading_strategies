from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Current schema label for the first canonical evaluation artifact slice.
EVALUATION_ARTIFACT_VERSION = "phase2.v1"

# The initial assembler only reads persisted evidence already stored in SQLite.
EVALUATION_SOURCE_MODE = "persisted_only"


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
    base_strategy: str | None = None
    active_strategy: str | None = None
    benchmark_ticker: str | None = None
    instrument_mode: str | None = None
    rotation_enabled: bool = False
    live_trading_enabled: bool = False


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
    rotation_episode_id: int | None = None
    episode_started_at: str | None = None
    episode_ended_at: str | None = None
    episode_realized_pnl_delta: float | None = None


@dataclass(frozen=True)
class EvaluationWalkForwardEvidence:
    available: bool = False
    grouped: bool = False
    run_ids: list[int] = field(default_factory=list)
    average_return_pct: float | None = None
    median_return_pct: float | None = None
    best_return_pct: float | None = None
    worst_return_pct: float | None = None


@dataclass(frozen=True)
class EvaluationConfidence:
    backtest_confidence: float = 0.0
    paper_live_confidence: float = 0.0
    overall_confidence: float = 0.0
    blended_score: float | None = None


@dataclass(frozen=True)
class EvaluationDiagnostics:
    data_gaps: list[str] = field(default_factory=list)


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
