from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import sqlite3

from common.time import parse_utc_iso
from common.time import utc_now_iso
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.domain.rotation_policy import evaluate_champion_challenger_rotation
from trading.models.rotation.rotation_decision import RotationDecision
from trading.models.rotation.rotation_score_weights import RotationScoreWeights
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.repositories.book_bridge import book_id_for_sleeve
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.sleeves import SleeveRepository

DEFAULT_ROLLING_WINDOW_DAYS = 30
DEFAULT_MIN_TRADES_IN_WINDOW = 20
DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS = 25.0
DEFAULT_ROTATION_COOLDOWN_DAYS = 7


@dataclass(frozen=True, slots=True)
class RotationPolicyConfig:
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
class RotationRunResult:
    sleeve_id: int
    decision_id: int
    decision_time: str
    decision: RotationDecision
    rotated: bool
    window_start_date: str
    window_end_date: str


def _weights_from_config(config: RotationPolicyConfig) -> RotationScoreWeights:
    return RotationScoreWeights(
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
    challengers: list[RotationStrategyMetrics],
) -> list[RotationStrategyMetrics]:
    normalized: list[RotationStrategyMetrics] = []
    for challenger in challengers:
        is_same_strategy = challenger.strategy_name == incumbent_strategy
        is_same_param_set = challenger.param_set_id == incumbent_param_set_id
        if is_same_strategy and is_same_param_set:
            continue
        normalized.append(challenger)
    return normalized


def book_cooldown_active(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    decision_time: str,
    cooldown_days: int,
) -> bool:
    """Whether the book is still within its post-rotation cooldown window.

    The unified "when" guard for both account and sleeve rotation: read the book's
    latest 'rotate' decision and compare against ``decision_time``.
    """
    latest_rotate = RotationDecisionRepository(conn).fetch_latest_rotate_action_for_book(book_id=int(book_id))
    latest_rotate_time = (
        str(latest_rotate["decision_time"]).strip()
        if latest_rotate is not None and latest_rotate["decision_time"] is not None
        else None
    )
    return _is_cooldown_active(
        latest_rotate_time=latest_rotate_time,
        decision_time=decision_time,
        cooldown_days=cooldown_days,
    )


def evaluate_book_rotation(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    incumbent: RotationStrategyMetrics,
    challengers: list[RotationStrategyMetrics],
    config: RotationPolicyConfig,
    cooldown_active: bool,
    decision_time: str,
) -> tuple[RotationDecision, int]:
    """Run champion/challenger for one book and record the decision on it.

    The shared book-keyed rotation core used by both the account (default book) and
    sleeve (bridging book) paths. Candidate enumeration and applying the winner stay
    caller-specific; this owns the policy call + the ``rotation_decisions`` audit.
    """
    decision = evaluate_champion_challenger_rotation(
        incumbent=incumbent,
        challengers=challengers,
        min_trades_in_window=max(1, int(config.min_trades_in_window)),
        outperformance_threshold_bps=float(config.outperformance_threshold_bps),
        cooldown_active=cooldown_active,
        weights=_weights_from_config(config),
    )
    decision_id = RotationDecisionRepository(conn).insert_for_book(
        book_id=int(book_id),
        decision_time=decision_time,
        incumbent_strategy=decision.incumbent_strategy,
        challenger_strategy=decision.challenger_strategy,
        selected_strategy=decision.selected_strategy,
        rotation_action=decision.rotation_action,
        cooldown_active=1 if decision.cooldown_active else 0,
        score_components_json=json.dumps(decision.score_components, sort_keys=True),
        gate_results_json=json.dumps(decision.gate_results, sort_keys=True),
        decision_reason=decision.decision_reason,
        config_version=config.config_version,
        created_at=decision_time,
    )
    return decision, decision_id


def evaluate_and_apply_sleeve_rotation(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    incumbent: RotationStrategyMetrics,
    challengers: list[RotationStrategyMetrics],
    config: RotationPolicyConfig = RotationPolicyConfig(),
    decision_time: str | None = None,
) -> RotationRunResult:
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
    book_id = book_id_for_sleeve(conn, int(sleeve_id), create=True)
    assert book_id is not None  # create=True always resolves a book id
    cooldown_active = book_cooldown_active(
        conn,
        book_id=book_id,
        decision_time=now_iso,
        cooldown_days=config.cooldown_days,
    )

    normalized_challengers = _normalize_challengers(
        incumbent_strategy=incumbent_strategy,
        incumbent_param_set_id=incumbent_param_set_id,
        challengers=challengers,
    )
    decision, decision_id = evaluate_book_rotation(
        conn,
        book_id=book_id,
        incumbent=incumbent,
        challengers=normalized_challengers,
        config=config,
        cooldown_active=cooldown_active,
        decision_time=now_iso,
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

    return RotationRunResult(
        sleeve_id=int(sleeve_id),
        decision_id=decision_id,
        decision_time=now_iso,
        decision=decision,
        rotated=rotated,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
    )
