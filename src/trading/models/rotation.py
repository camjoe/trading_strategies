"""Strategy-rotation data contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookRotationConfig:
    """Caller-facing book rotation-scheduling input (profiles / admin API).

    Fields mirror the book-owned scheduling columns (ADR 014): the enabled
    gate, the challenger schedule, and the evidence lookback. ``None`` means
    the caller did not supply the field.
    """

    enabled: bool | None = None
    schedule: list[str] | None = None
    lookback_days: int | None = None

    def to_db_dict(self) -> dict[str, object]:
        """Map fields to ``book_rotation_settings`` column values.

        The list-valued ``rotation_schedule`` column is returned as a raw
        list; JSON encoding is applied by the writer via
        ``trading.domain.rotation.schedule.dump_rotation_schedule``.
        """
        return {
            "rotation_enabled": self.enabled,
            "rotation_schedule": self.schedule,
            "rotation_lookback_days": self.lookback_days,
        }


@dataclass(frozen=True, slots=True)
class RotationScoreWeights:
    risk_adjusted_return_weight: float = 1.0
    stability_weight: float = 0.25
    drawdown_penalty_weight: float = 0.20
    regime_fit_weight: float = 0.10


@dataclass(frozen=True, slots=True)
class RotationStrategyMetrics:
    strategy_name: str
    trade_count: int
    risk_adjusted_return: float
    stability: float
    drawdown_penalty: float
    regime_fit: float


@dataclass(frozen=True, slots=True)
class RotationStrategyScore:
    strategy_name: str
    score: float
    score_components: dict[str, float]
    trade_count: int
    risk_adjusted_return: float


@dataclass(frozen=True, slots=True)
class RotationDecision:
    rotation_action: str
    selected_strategy: str
    incumbent_strategy: str
    challenger_strategy: str | None
    cooldown_active: bool
    decision_reason: str
    score_components: dict[str, dict[str, float]]
    gate_results: dict[str, object]
