"""Persistence for walk-forward optimizer experiments (Tier-1).

One row per ``backtest-optimize`` run in ``optimization_experiments``: the run
config, the forward-carried winner parameters (the promotion candidate), a small
OOS aggregate, the untouched-holdout summary, and the promoted-variant link. This
is the auditable basis a later promotion resolves the winner from. Per-window and
per-candidate detail are intentionally not stored (see revision ``0021``).
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.backtesting.optimizer_models import (
    OptimizationExperimentInsert,
    OptimizationExperimentRecord,
)
from trading.repositories.unit_of_work import commit_unit_of_work

_SELECT = "SELECT * FROM optimization_experiments"


def insert_experiment(
    conn: sqlite3.Connection,
    payload: OptimizationExperimentInsert,
    *,
    created_at: str | None = None,
) -> int:
    """Insert one experiment row and return its id.

    Participates in the caller's ``unit_of_work``: commits standalone, or defers
    inside a scope so it lands atomically with the run's other writes.
    """
    now = created_at or utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO optimization_experiments (
            account_id, strategy_id, primitive, objective_name, search_space_json,
            candidate_budget, train_months, test_months, step_months, holdout_months,
            warmup_months, start_date, end_date, window_count, winner_params_json,
            oos_mean_winner_return_pct, oos_mean_baseline_return_pct, oos_windows_beat_baseline,
            holdout_run_id, holdout_winner_return_pct, holdout_baseline_return_pct,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload.account_id),
            payload.strategy_id if payload.strategy_id is None else int(payload.strategy_id),
            payload.primitive,
            payload.objective_name,
            payload.search_space_json,
            int(payload.candidate_budget),
            int(payload.train_months),
            int(payload.test_months),
            int(payload.step_months),
            int(payload.holdout_months),
            int(payload.warmup_months),
            payload.start_date,
            payload.end_date,
            int(payload.window_count),
            payload.winner_params_json,
            payload.oos_mean_winner_return_pct,
            payload.oos_mean_baseline_return_pct,
            payload.oos_windows_beat_baseline,
            payload.holdout_run_id,
            payload.holdout_winner_return_pct,
            payload.holdout_baseline_return_pct,
            now,
        ),
    )
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def fetch_experiment_by_id(conn: sqlite3.Connection, *, experiment_id: int) -> OptimizationExperimentRecord | None:
    row = conn.execute(_SELECT + " WHERE id = ?", (int(experiment_id),)).fetchone()
    return OptimizationExperimentRecord.from_mapping(dict(row)) if row is not None else None


def fetch_latest_for_account(conn: sqlite3.Connection, *, account_id: int) -> OptimizationExperimentRecord | None:
    row = conn.execute(
        _SELECT + " WHERE account_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(account_id),),
    ).fetchone()
    return OptimizationExperimentRecord.from_mapping(dict(row)) if row is not None else None


def set_promoted_strategy(conn: sqlite3.Connection, *, experiment_id: int, strategy_id: int) -> None:
    """Record the tradeable variant an experiment's winner was promoted into."""
    conn.execute(
        "UPDATE optimization_experiments SET promoted_strategy_id = ? WHERE id = ?",
        (int(strategy_id), int(experiment_id)),
    )
    commit_unit_of_work(conn)
