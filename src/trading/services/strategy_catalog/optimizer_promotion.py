"""Promote a walk-forward optimization winner into a tradeable strategy variant.

Closes the operational optimize -> promote loop: take a persisted
``optimization_experiments`` row, mint a new ``strategies`` variant from its
forward-carried winner parameters (validated against the base primitive), and
record the audit link back to the experiment. The variant is frozen by default
(evidence-backed -> immutable) and, being enabled, is immediately a first-class
catalog strategy available to rotation/assignment.

The gate is **quality-gated by default**: the winner must beat its own default on
OOS evidence (mean return and a majority of windows) and on the untouched holdout
(see ``evaluate_promotion_gate``) — see ``docs/reference/backtesting.md`` for the
exact bar. ``allow_no_edge=True`` bypasses the bar (e.g. to prove the promotion
mechanism works before any edge exists), leaving only the existence/failed/
already-promoted checks.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from trading.backtesting.optimizer_models import ExperimentStatus, OptimizationExperimentRecord
from trading.backtesting.repositories.optimization_repository import (
    fetch_experiment_by_id,
    set_promoted_strategy,
)
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.domain.promotion_gate import evaluate_promotion_gate
from trading.models.strategy import StrategyRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.services.strategy_catalog.mutations import create_strategy_variant, freeze_strategy


def promote_optimization_experiment(
    conn: sqlite3.Connection,
    *,
    experiment_id: int,
    new_strategy_key: str,
    freeze: bool = True,
    allow_no_edge: bool = False,
    now_iso: str | None = None,
) -> StrategyRecord:
    """Mint a tradeable variant from an experiment's winner and link it back.

    Raises ``NotFoundError`` if the experiment is unknown, and ``ValueError`` if it
    failed (no winner to promote), was already promoted (one promotion per
    experiment keeps the audit link 1:1), does not clear the promotion quality bar
    (unless ``allow_no_edge=True``), or if the target key already exists. Variant
    creation, the optional freeze, and the promoted-link write land atomically.
    """
    experiment = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    if experiment is None:
        raise NotFoundError(f"Optimization experiment not found: {experiment_id}")
    if experiment.status == ExperimentStatus.FAILED:
        raise ValidationError(f"Experiment {experiment_id} failed ({experiment.failure_stage}); nothing to promote.")
    if experiment.promoted_strategy_id is not None:
        raise ValueError(
            f"Experiment {experiment_id} is already promoted (strategy id {experiment.promoted_strategy_id})."
        )
    if not allow_no_edge:
        gate = evaluate_promotion_gate(
            oos_mean_winner_return_pct=experiment.oos_mean_winner_return_pct,
            oos_mean_baseline_return_pct=experiment.oos_mean_baseline_return_pct,
            oos_windows_beat_baseline=experiment.oos_windows_beat_baseline,
            window_count=experiment.window_count,
            holdout_winner_return_pct=experiment.holdout_winner_return_pct,
            holdout_baseline_return_pct=experiment.holdout_baseline_return_pct,
        )
        if not gate.passed:
            raise ValidationError(
                f"Experiment {experiment_id} does not clear the promotion quality bar: "
                f"{'; '.join(gate.reasons)}. Use --allow-no-edge to promote anyway."
            )

    winner_params: dict[str, Any] = json.loads(experiment.winner_params_json)

    with unit_of_work(conn):
        variant = create_strategy_variant(
            conn,
            strategy_key=new_strategy_key,
            primitive=experiment.primitive,
            params=winner_params or None,
            description=_provenance(experiment),
            now_iso=now_iso,
        )
        if freeze:
            variant = freeze_strategy(conn, strategy_key=new_strategy_key, now_iso=now_iso)
        set_promoted_strategy(conn, experiment_id=experiment_id, strategy_id=variant.id)
    return variant


def _provenance(experiment: OptimizationExperimentRecord) -> str:
    """Human-readable provenance stamped onto the promoted variant's description."""
    parts = [
        f"Promoted from optimization experiment #{experiment.id}",
        f"primitive={experiment.primitive}",
        f"objective={experiment.objective_name}",
    ]
    if experiment.holdout_winner_return_pct is not None and experiment.holdout_baseline_return_pct is not None:
        parts.append(
            f"holdout winner {experiment.holdout_winner_return_pct:.2f}% "
            f"vs default {experiment.holdout_baseline_return_pct:.2f}%"
        )
    parts.append(experiment.created_at)
    return "; ".join(parts)
