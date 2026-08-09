"""One experiment's persisted audit record, joined from this package's tables.

One of the two seams the trading side reads (the other is
:mod:`backtesting.services.evidence`).

``fetch_recent_experiments`` forwards to the repository unchanged, and has to:
``layer_check`` bars ``src/trading/`` from this package's repositories, and its
one caller joins account names, which backtesting does not own.

Repository reads are module-qualified because both packages use the same
``fetch_*`` verbs, so a forward collides with the name it forwards to.
"""

from __future__ import annotations

import sqlite3

from backtesting.models.optimizer import (
    ExperimentAudit,
    ExperimentStatus,
    ExperimentWindowAudit,
    OptimizationExperimentRecord,
    OptimizationTrialRecord,
)
from backtesting.repositories import optimization
from backtesting.services.optimizer_aggregation import fetch_compounded_oos


def fetch_recent_experiments(conn: sqlite3.Connection, *, limit: int) -> list[OptimizationExperimentRecord]:
    """Most recent experiments first."""
    return optimization.fetch_recent_experiments(conn, limit=limit)


def fetch_experiment_audit(conn: sqlite3.Connection, *, experiment_id: int) -> ExperimentAudit | None:
    """Assemble one experiment's audit record, or ``None`` if unknown.

    Trials are nested under the window they were evaluated on rather than returned
    flat, so the multiple-testing record reads in the order the search happened.
    """
    experiment = optimization.fetch_experiment_by_id(conn, experiment_id=experiment_id)
    if experiment is None:
        return None

    if experiment.status == ExperimentStatus.FAILED:
        return ExperimentAudit(experiment=experiment, windows=[], compounded_oos=None, manifest=None)

    trials_by_window: dict[int, list[OptimizationTrialRecord]] = {}
    for trial in optimization.fetch_trials_for_experiment(conn, experiment_id=experiment_id):
        trials_by_window.setdefault(trial.window_id, []).append(trial)

    return ExperimentAudit(
        experiment=experiment,
        windows=[
            ExperimentWindowAudit(window=window, trials=trials_by_window.get(window.id, []))
            for window in optimization.fetch_windows_for_experiment(conn, experiment_id=experiment_id)
        ],
        compounded_oos=fetch_compounded_oos(conn, experiment_id=experiment_id),
        manifest=optimization.fetch_manifest_for_experiment(conn, experiment_id=experiment_id),
    )
