from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from common.json_columns import dumps_json_column
from common.time import parse_utc_iso, utc_now_iso
from trading.domain.rotation.policy import evaluate_champion_challenger_rotation
from trading.domain.rotation.schedule import dump_rotation_schedule, parse_rotation_schedule
from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.books import BookRotationSettingsRecord
from trading.models.rotation import RotationDecision, RotationScoreWeights, RotationStrategyMetrics
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.services.books.book_assignments import assign_book_strategy, open_assignment_for_book

DEFAULT_ROLLING_WINDOW_DAYS = 30
DEFAULT_MIN_TRADES_IN_WINDOW = 20
DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS = 25.0
DEFAULT_ROTATION_COOLDOWN_DAYS = 7


# Scoring weights default to the model's, so the flat fields here and
# RotationScoreWeights cannot drift into two different untuned policies.
_DEFAULT_WEIGHTS = RotationScoreWeights()


@dataclass(frozen=True, slots=True)
class RotationPolicyConfig:
    rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS
    min_trades_in_window: int = DEFAULT_MIN_TRADES_IN_WINDOW
    outperformance_threshold_bps: float = DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS
    cooldown_days: int = DEFAULT_ROTATION_COOLDOWN_DAYS
    config_version: str | None = None
    risk_adjusted_return_weight: float = _DEFAULT_WEIGHTS.risk_adjusted_return_weight
    stability_weight: float = _DEFAULT_WEIGHTS.stability_weight
    drawdown_penalty_weight: float = _DEFAULT_WEIGHTS.drawdown_penalty_weight
    regime_fit_weight: float = _DEFAULT_WEIGHTS.regime_fit_weight


@dataclass(frozen=True, slots=True)
class RotationRunResult:
    # The rotated trading book — the primary key of the flow.
    book_id: int
    decision_id: int
    decision_time: str
    decision: RotationDecision
    rotated: bool


@dataclass(frozen=True, slots=True)
class BookRotationScheduleConfig:
    """The book's effective rotation-scheduling inputs (ADR 014).

    Code defaults describe an untuned book: rotation disabled, no challenger
    schedule (incumbent-only), default evidence window.
    """

    rotation_enabled: bool = False
    schedule: tuple[str, ...] = ()
    lookback_days: int = DEFAULT_ROLLING_WINDOW_DAYS


def resolve_book_rotation_schedule(conn: sqlite3.Connection, *, book_id: int) -> BookRotationScheduleConfig:
    """Resolve the book's effective rotation scheduling.

    Reads the book's ``book_rotation_settings`` scheduling columns; NULL
    fields (and a missing row) fall back to the ``BookRotationScheduleConfig``
    code defaults. A malformed schedule value degrades to no challengers
    rather than failing the run.
    """
    record = BookRotationSettingsRepository(conn).fetch(book_id=int(book_id))
    if record is None:
        return BookRotationScheduleConfig()
    try:
        schedule = tuple(name for name in parse_rotation_schedule(record.rotation_schedule) if name)
    except ValueError:
        schedule = ()
    lookback = record.rotation_lookback_days
    return BookRotationScheduleConfig(
        rotation_enabled=bool(record.rotation_enabled),
        schedule=schedule,
        lookback_days=(int(lookback) if lookback is not None and int(lookback) > 0 else DEFAULT_ROLLING_WINDOW_DAYS),
    )


def resolve_default_book_rotation_schedule(conn: sqlite3.Connection, *, account_id: int) -> BookRotationScheduleConfig:
    """The account's default-book rotation scheduling, read-only.

    A missing default book resolves to the untuned code defaults (rotation
    disabled) — it is never bootstrapped from a read path.
    """
    book = BookRepository(conn).fetch_default_for_account(account_id=int(account_id))
    if book is None:
        return BookRotationScheduleConfig()
    return resolve_book_rotation_schedule(conn, book_id=book.id)


def write_book_rotation_scheduling(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    updates: Mapping[str, object],
) -> BookRotationSettingsRecord:
    """Merge scheduling ``updates`` over the book's persisted row and save.

    The single writer behind both the operator edit surface
    (``parameters.update_book_rotation_scheduling``) and the profile-import
    surface (``config_parser.apply_book_rotation_settings``). Keys absent from
    ``updates`` keep their persisted values (partial edit); ``rotation_schedule``
    takes a list of strategy names (validated) or None for no challengers;
    ``rotation_lookback_days`` None falls back to the code default. Returns the
    persisted row.
    """
    repository = BookRotationSettingsRepository(conn)
    current = repository.fetch(book_id=book_id)

    if "rotation_enabled" in updates:
        enabled = int(bool(updates["rotation_enabled"]))
    else:
        enabled = int(current.rotation_enabled) if current is not None else 0
    if "rotation_lookback_days" in updates:
        raw_lookback = updates["rotation_lookback_days"]
        if raw_lookback is None:
            lookback = None
        elif isinstance(raw_lookback, int):
            lookback = raw_lookback
        else:
            raise ValueError("rotation_lookback_days must be an integer or None")
        if lookback is not None and lookback <= 0:
            raise ValueError("rotation_lookback_days must be > 0")
    else:
        lookback = current.rotation_lookback_days if current is not None else None
    if "rotation_schedule" in updates:
        names = parse_rotation_schedule(updates["rotation_schedule"])
        for name in names:
            validate_strategy_name(name)
        schedule = dump_rotation_schedule(names) if names else None
    else:
        schedule = current.rotation_schedule if current is not None else None

    now_iso = utc_now_iso()
    repository.upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=enabled,
        rotation_lookback_days=lookback,
        rotation_schedule=schedule,
        created_at=current.created_at if current is not None else now_iso,
        updated_at=now_iso,
    )
    saved = repository.fetch(book_id=book_id)
    if saved is None:
        raise RuntimeError(f"book_rotation_settings row missing after upsert for book_id={book_id}")
    return saved


def _tuned[T](stored: T | None, default: T) -> T:
    """The book's stored setting, or the code default when the column is NULL.

    A NULL column means untuned, so it falls back; ``0`` and ``0.0`` are real
    operator choices and must not.
    """
    return default if stored is None else stored


def resolve_rotation_policy_config(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    rolling_window_days: int,
    config_version: str | None = None,
) -> RotationPolicyConfig:
    """Resolve the book's effective rotation policy.

    Reads the book's ``book_rotation_settings`` policy columns; NULL fields
    (and a missing row) fall back to the ``RotationPolicyConfig`` code
    defaults, so an untuned book behaves exactly as before the migration.
    """
    defaults = RotationPolicyConfig()
    record = BookRotationSettingsRepository(conn).fetch(book_id=int(book_id))
    if record is None:
        return RotationPolicyConfig(rolling_window_days=rolling_window_days, config_version=config_version)
    return RotationPolicyConfig(
        rolling_window_days=rolling_window_days,
        config_version=config_version,
        min_trades_in_window=_tuned(record.min_trades_in_window, defaults.min_trades_in_window),
        outperformance_threshold_bps=_tuned(
            record.outperformance_threshold_bps, defaults.outperformance_threshold_bps
        ),
        cooldown_days=_tuned(record.cooldown_days, defaults.cooldown_days),
        risk_adjusted_return_weight=_tuned(record.risk_adjusted_return_weight, defaults.risk_adjusted_return_weight),
        stability_weight=_tuned(record.stability_weight, defaults.stability_weight),
        drawdown_penalty_weight=_tuned(record.drawdown_penalty_weight, defaults.drawdown_penalty_weight),
        regime_fit_weight=_tuned(record.regime_fit_weight, defaults.regime_fit_weight),
    )


def _weights_from_config(config: RotationPolicyConfig) -> RotationScoreWeights:
    return RotationScoreWeights(
        risk_adjusted_return_weight=float(config.risk_adjusted_return_weight),
        stability_weight=float(config.stability_weight),
        drawdown_penalty_weight=float(config.drawdown_penalty_weight),
        regime_fit_weight=float(config.regime_fit_weight),
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
    challengers: list[RotationStrategyMetrics],
) -> list[RotationStrategyMetrics]:
    return [challenger for challenger in challengers if challenger.strategy_name != incumbent_strategy]


def _book_cooldown_active(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    decision_time: str,
    cooldown_days: int,
) -> bool:
    """Whether the book is still within its post-rotation cooldown window.

    The unified "when" guard for book rotation: read the book's
    latest 'rotate' decision and compare against ``decision_time``.
    """
    latest_rotate_time = RotationDecisionRepository(conn).fetch_latest_rotate_time_for_book(book_id=int(book_id))
    return _is_cooldown_active(
        latest_rotate_time=latest_rotate_time,
        decision_time=decision_time,
        cooldown_days=cooldown_days,
    )


def _evaluate_book_rotation(
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

    The shared book-keyed rotation core used by every book (the default book and any
    additional books alike). Candidate enumeration and applying the winner stay
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
        score_components_json=dumps_json_column(decision.score_components),
        gate_results_json=dumps_json_column(decision.gate_results),
        decision_reason=decision.decision_reason,
        config_version=config.config_version,
        created_at=decision_time,
    )
    return decision, decision_id


def evaluate_and_apply_book_rotation(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    incumbent: RotationStrategyMetrics,
    challengers: list[RotationStrategyMetrics],
    config: RotationPolicyConfig = RotationPolicyConfig(),
    decision_time: str | None = None,
) -> RotationRunResult:
    now_iso = decision_time or utc_now_iso()
    # Book assignments are the single live assignment record.
    assignment = open_assignment_for_book(conn, book_id=int(book_id))
    if assignment is None:
        raise ValueError(f"No incumbent assignment found for book_id={book_id}.")

    incumbent_strategy = assignment.strategy_name.strip()
    cooldown_active = _book_cooldown_active(
        conn,
        book_id=book_id,
        decision_time=now_iso,
        cooldown_days=config.cooldown_days,
    )

    normalized_challengers = _normalize_challengers(
        incumbent_strategy=incumbent_strategy,
        challengers=challengers,
    )
    with unit_of_work(conn):
        decision, decision_id = _evaluate_book_rotation(
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
            assign_book_strategy(
                conn,
                book_id=int(book_id),
                strategy_name=decision.selected_strategy,
                now_iso=now_iso,
            )
            rotated = True

    return RotationRunResult(
        book_id=int(book_id),
        decision_id=decision_id,
        decision_time=now_iso,
        decision=decision,
        rotated=rotated,
    )
