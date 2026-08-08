"""One experiment's persisted audit record, assembled from this package's tables.

The second half of the read surface the trading side uses (the first is
:mod:`backtesting.services.evidence_service`). An operator surface wants
"everything recorded about this run"; how experiments, windows, trials, the
compounded OOS series, and the run manifest relate is this package's business, so
the joining happens here and the caller gets a finished record.

``fetch_recent_experiments`` forwards to the repository without adding anything.
That is deliberate: it belongs to the same read surface as the audit assembly, and
splitting the pair — one through a service, one reaching into the tables — would
leave the boundary half-drawn for no gain. It is a public entrypoint for the
context, not indirection inside a layer stack.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from backtesting.models.optimizer import (
    CompoundedOOSSeries,
    ExperimentStatus,
    OptimizationExperimentRecord,
    OptimizationManifestRecord,
    OptimizationTrialRecord,
    OptimizationWindowRecord,
)
from backtesting.repositories.optimization import (
    fetch_experiment_by_id,
    fetch_manifest_for_experiment,
    fetch_recent_experiments as _fetch_recent_experiments,
    fetch_trials_for_experiment,
    fetch_windows_for_experiment,
)
from backtesting.services.optimizer_aggregation_service import fetch_compounded_oos


@dataclass(frozen=True)
class ExperimentWindowAudit:
    """One walk-forward window and every candidate evaluated on its training interval."""

    window: OptimizationWindowRecord
    trials: list[OptimizationTrialRecord]


@dataclass(frozen=True)
class ExperimentAudit:
    """Everything this package persisted about one experiment.

    A failed experiment carries no windows, trials, compounded series, or manifest —
    it never got far enough to persist an audit tree.
    """

    experiment: OptimizationExperimentRecord
    windows: list[ExperimentWindowAudit]
    compounded_oos: CompoundedOOSSeries | None
    manifest: OptimizationManifestRecord | None


def fetch_recent_experiments(conn: sqlite3.Connection, *, limit: int) -> list[OptimizationExperimentRecord]:
    """Most recent experiments first."""
    return _fetch_recent_experiments(conn, limit=limit)


def fetch_experiment_audit(conn: sqlite3.Connection, *, experiment_id: int) -> ExperimentAudit | None:
    """Assemble one experiment's audit record, or ``None`` if unknown.

    Trials are nested under the window they were evaluated on rather than returned
    flat, so the multiple-testing record reads in the order the search happened.
    """
    experiment = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    if experiment is None:
        return None

    if experiment.status == ExperimentStatus.FAILED:
        return ExperimentAudit(experiment=experiment, windows=[], compounded_oos=None, manifest=None)

    trials_by_window: dict[int, list[OptimizationTrialRecord]] = {}
    for trial in fetch_trials_for_experiment(conn, experiment_id=experiment_id):
        trials_by_window.setdefault(trial.window_id, []).append(trial)

    return ExperimentAudit(
        experiment=experiment,
        windows=[
            ExperimentWindowAudit(window=window, trials=trials_by_window.get(window.id, []))
            for window in fetch_windows_for_experiment(conn, experiment_id=experiment_id)
        ],
        compounded_oos=fetch_compounded_oos(conn, experiment_id=experiment_id),
        manifest=fetch_manifest_for_experiment(conn, experiment_id=experiment_id),
    )
