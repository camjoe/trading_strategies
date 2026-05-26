from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import sqlite3

from common.coercion import row_int
from common.time import parse_utc_iso
from common.time import utc_now_iso
from trading.services.sleeves.helpers import mean as _sleeve_mean
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.domain.sleeve_rotation import (
    SleeveRotationDecision,
    SleeveRotationScoreWeights,
    SleeveStrategyMetrics,
    evaluate_champion_challenger_rotation,
)
from trading.repositories.daily_metrics import fetch_daily_metrics_for_sleeve_window
from trading.repositories.rotation_decisions import (
    fetch_latest_rotate_decision_for_sleeve,
    insert_rotation_decision,
)
from trading.repositories.sleeves import (
    close_active_sleeve_strategy_assignment,
    fetch_active_sleeve_strategy_assignment,
    insert_sleeve_strategy_assignment,
)

# Convert basis points to percentage points for cost-penalty normalization.
BASIS_POINTS_TO_PERCENT = 0.01

# Default rolling window for incumbent/challenger comparison.
DEFAULT_ROLLING_WINDOW_DAYS = 30

# Require this minimum observed trade count before a challenger can rotate in.
DEFAULT_MIN_TRADES_IN_WINDOW = 20

# Challenger must beat incumbent by this many basis points to rotate.
DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS = 25.0

# Cooldown period after a successful rotate decision.
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


def _average(values: list[float]) -> float:
    return _sleeve_mean(values)


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


def _build_incumbent_metrics(
    *,
    strategy_name: str,
    param_set_id: int | None,
    rows: list[sqlite3.Row],
) -> SleeveStrategyMetrics:
    risk_adjusted_scores = [
        float(row["risk_adjusted_score"]) for row in rows if row["risk_adjusted_score"] is not None
    ]
    return_pcts = [float(row["return_pct"]) for row in rows if row["return_pct"] is not None]
    hit_rates = [float(row["hit_rate"]) for row in rows if row["hit_rate"] is not None]
    drawdown_values = [float(row["drawdown_pct"]) for row in rows if row["drawdown_pct"] is not None]
    slippage_bps_values = [float(row["slippage_bps"]) for row in rows if row["slippage_bps"] is not None]
    trade_count = sum(int(row["trade_count"]) for row in rows if row["trade_count"] is not None)
    drawdown_penalty = abs(min(drawdown_values)) if drawdown_values else 0.0

    risk_adjusted_return = _average(risk_adjusted_scores) if risk_adjusted_scores else _average(return_pcts)
    stability = _average(hit_rates)
    cost_penalty = _average(slippage_bps_values) * BASIS_POINTS_TO_PERCENT
    return SleeveStrategyMetrics(
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        trade_count=trade_count,
        risk_adjusted_return=risk_adjusted_return,
        stability=stability,
        drawdown_penalty=drawdown_penalty,
        cost_penalty=cost_penalty,
        regime_fit=0.0,
    )


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
    challengers: list[SleeveStrategyMetrics],
    config: SleeveRotationConfig = SleeveRotationConfig(),
    decision_time: str | None = None,
) -> SleeveRotationRunResult:
    now_iso = decision_time or utc_now_iso()
    assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=int(sleeve_id))
    if assignment is None:
        raise ValueError(f"No incumbent assignment found for sleeve_id={sleeve_id}.")

    incumbent_strategy = str(assignment["strategy_name"]).strip()
    incumbent_param_set_id = row_int(assignment, "param_set_id")
    window_start_date, window_end_date = _resolve_window_bounds(
        as_of_iso=now_iso,
        rolling_window_days=max(1, int(config.rolling_window_days)),
    )
    metric_rows = fetch_daily_metrics_for_sleeve_window(
        conn,
        sleeve_id=int(sleeve_id),
        start_date=window_start_date,
        end_date=window_end_date,
    )
    incumbent_metrics = _build_incumbent_metrics(
        strategy_name=incumbent_strategy,
        param_set_id=incumbent_param_set_id,
        rows=metric_rows,
    )
    latest_rotate = fetch_latest_rotate_decision_for_sleeve(conn, sleeve_id=int(sleeve_id))
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
        incumbent=incumbent_metrics,
        challengers=normalized_challengers,
        min_trades_in_window=max(1, int(config.min_trades_in_window)),
        outperformance_threshold_bps=float(config.outperformance_threshold_bps),
        cooldown_active=cooldown_active,
        weights=_weights_from_config(config),
    )
    decision_id = insert_rotation_decision(
        conn,
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
        close_active_sleeve_strategy_assignment(
            conn,
            sleeve_id=int(sleeve_id),
            effective_to=now_iso,
            updated_at=now_iso,
        )
        insert_sleeve_strategy_assignment(
            conn,
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
