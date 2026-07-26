"""Promote a walk-forward optimization winner into a tradeable strategy variant.

Closes the operational optimize -> promote loop: take a persisted
``optimization_experiments`` row, mint a new ``strategies`` variant from its
forward-carried winner parameters (validated against the base primitive), and
record the audit link back to the experiment. The variant is frozen by default
(evidence-backed -> immutable) and, being enabled, is immediately a first-class
catalog strategy available to rotation/assignment.

The gate is **operational completeness only**: the experiment must exist and not be
already promoted. No out-of-sample edge is required — a tuned winner that did not
beat its default is still promotable; its recorded holdout/OOS evidence is for the
operator to judge, not an automated bar.
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
from trading.models.strategy.strategy_record import StrategyRecord
from trading.repositories.unit_of_work import unit_of_work
from trading.services.strategy_catalog.mutations import create_strategy_variant, freeze_strategy


def promote_optimization_experiment(
    conn: sqlite3.Connection,
    *,
    experiment_id: int,
    new_strategy_key: str,
    freeze: bool = True,
    now_iso: str | None = None,
) -> StrategyRecord:
    """Mint a tradeable variant from an experiment's winner and link it back.

    Raises ``NotFoundError`` if the experiment is unknown, and ``ValueError`` if it
    failed (no winner to promote), was already promoted (one promotion per
    experiment keeps the audit link 1:1), or if the target key already exists.
    Variant creation, the optional freeze, and the promoted-link write land
    atomically.
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
