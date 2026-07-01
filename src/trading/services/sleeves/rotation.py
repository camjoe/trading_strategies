from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import sqlite3

from common.time import parse_utc_iso
from common.time import utc_now_iso
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.domain.sleeve_rotation import evaluate_champion_challenger_rotation
from trading.models.sleeves.sleeve_rotation_decision import SleeveRotationDecision
from trading.models.sleeves.sleeve_rotation_score_weights import SleeveRotationScoreWeights
from trading.models.sleeves.sleeve_strategy_metrics import SleeveStrategyMetrics
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.sleeves import SleeveRepository

DEFAULT_ROLLING_WINDOW_DAYS = 30
DEFAULT_MIN_TRADES_IN_WINDOW = 20
DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS = 25.0
DEFAULT_ROTATION_COOLDOWN_DAYS = 7


@dataclass(frozen=True, slots=True)
class SleeveRotationConfig:
    rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS
    min_trades_in_window: int = DEFAULT_MIN_TRADES_IN_WINDOW
    outperformance_threshold_bps: float = DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS
    cooldown_days: int = DEFAULT_ROTATION_COOLDOWN_DAYS
    config_version: str | None = None
    risk_adjusted_return_weight: float = 1.0
    stability_weight: float = 0.25
    drawdown_penalty_weight: float = 0.20
    cost_penalty_weight: float = 0.10
    regime_fit_weight: float = 0.10


@dataclass(frozen=True, slots=True)
class SleeveRotationRunResult:
    sleeve_id: int
    decision_id: int
    decision_time: str
    decision: SleeveRotationDecision
    rotated: bool
    window_start_date: str
    window_end_date: str


def _weights_from_config(config: SleeveRotationConfig) -> SleeveRotationScoreWeights:
    return SleeveRotationScoreWeights(
        risk_adjusted_return_weight=float(config.risk_adjusted_return_weight),
        stability_weight=float(config.stability_weight),
        drawdown_penalty_weight=float(config.drawdown_penalty_weight),
        cost_penalty_weight=float(config.cost_penalty_weight),
        regime_fit_weight=float(config.regime_fit_weight),
    )


def _resolve_window_bounds(*, as_of_iso: str, rolling_window_days: int) -> tuple[str, str]:
    return _resolve_window_bounds_shared(as_of_iso=as_of_iso, rolling_window_days=rolling_window_days)


def _is_cooldown_active(
    *,
    latest_rotate_time: str | None,
    decision_time: str,
    cooldown_days: int,
) -> bool:
    if not latest_rotate_time:
        return False
    cooldown_window_days = max(0, int(cooldown_days))
    if cooldown_window_days <= 0:
        return False
    latest_dt = parse_utc_iso(latest_rotate_time)
    current_dt = parse_utc_iso(decision_time)
    elapsed = current_dt - latest_dt
    return elapsed < timedelta(days=cooldown_window_days)


def _normalize_challengers(
    *,
    incumbent_strategy: str,
    incumbent_param_set_id: int | None,
    challengers: list[SleeveStrategyMetrics],
) -> list[SleeveStrategyMetrics]:
    normalized: list[SleeveStrategyMetrics] = []
    for challenger in challengers:
        is_same_strategy = challenger.strategy_name == incumbent_strategy
        is_same_param_set = challenger.param_set_id == incumbent_param_set_id
        if is_same_strategy and is_same_param_set:
            continue
        normalized.append(challenger)
    return normalized


def evaluate_and_apply_sleeve_rotation(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    incumbent: SleeveStrategyMetrics,
    challengers: list[SleeveStrategyMetrics],
    config: SleeveRotationConfig = SleeveRotationConfig(),
    decision_time: str | None = None,
) -> SleeveRotationRunResult:
    now_iso = decision_time or utc_now_iso()
    sleeve_repo = SleeveRepository(conn)
    assignment = sleeve_repo.fetch_active_assignment(sleeve_id=int(sleeve_id))
    if assignment is None:
        raise ValueError(f"No incumbent assignment found for sleeve_id={sleeve_id}.")

    incumbent_strategy = assignment.strategy_name.strip()
    incumbent_param_set_id = assignment.param_set_id
    window_start_date, window_end_date = _resolve_window_bounds(
        as_of_iso=now_iso,
        rolling_window_days=max(1, int(config.rolling_window_days)),
    )
    latest_rotate = RotationDecisionRepository(conn).fetch_latest_rotate_action(sleeve_id=int(sleeve_id))
    latest_rotate_time = (
        str(latest_rotate["decision_time"]).strip()
        if latest_rotate is not None and latest_rotate["decision_time"] is not None
        else None
    )
    cooldown_active = _is_cooldown_active(
        latest_rotate_time=latest_rotate_time,
        decision_time=now_iso,
        cooldown_days=config.cooldown_days,
    )

    normalized_challengers = _normalize_challengers(
        incumbent_strategy=incumbent_strategy,
        incumbent_param_set_id=incumbent_param_set_id,
        challengers=challengers,
    )
    decision = evaluate_champion_challenger_rotation(
        incumbent=incumbent,
        challengers=normalized_challengers,
        min_trades_in_window=max(1, int(config.min_trades_in_window)),
        outperformance_threshold_bps=float(config.outperformance_threshold_bps),
        cooldown_active=cooldown_active,
        weights=_weights_from_config(config),
    )
    decision_id = RotationDecisionRepository(conn).insert(
        sleeve_id=int(sleeve_id),
        decision_time=now_iso,
        incumbent_strategy=decision.incumbent_strategy,
        challenger_strategy=decision.challenger_strategy,
        selected_strategy=decision.selected_strategy,
        rotation_action=decision.rotation_action,
        cooldown_active=1 if decision.cooldown_active else 0,
        score_components_json=json.dumps(decision.score_components, sort_keys=True),
        gate_results_json=json.dumps(decision.gate_results, sort_keys=True),
        decision_reason=decision.decision_reason,
        config_version=config.config_version,
        param_set_id=decision.selected_param_set_id,
        created_at=now_iso,
    )

    rotated = False
    if decision.rotation_action == "rotate":
        sleeve_repo.close_active_assignment(
            sleeve_id=int(sleeve_id),
            effective_to=now_iso,
            updated_at=now_iso,
        )
        sleeve_repo.insert_assignment(
            sleeve_id=int(sleeve_id),
            strategy_name=decision.selected_strategy,
            param_set_id=decision.selected_param_set_id,
            effective_from=now_iso,
            effective_to=None,
            is_incumbent=1,
            created_at=now_iso,
            updated_at=now_iso,
        )
        rotated = True

    return SleeveRotationRunResult(
        sleeve_id=int(sleeve_id),
        decision_id=decision_id,
        decision_time=now_iso,
        decision=decision,
        rotated=rotated,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
    )
