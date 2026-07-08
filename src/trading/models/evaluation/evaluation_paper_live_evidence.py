from __future__ import annotations

from dataclasses import dataclass


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
    # rotation_decisions boundaries); named episode_* for now, renamed in the P5 pass.
    episode_started_at: str | None = None
    episode_ended_at: str | None = None
