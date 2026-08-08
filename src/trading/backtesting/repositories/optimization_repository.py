"""Persistence for walk-forward optimizer experiments.

One row per ``backtest-optimize`` run in ``optimization_experiments``: the run
config, the forward-carried winner parameters (the promotion candidate), a small
OOS aggregate, the untouched-holdout summary, and the promoted-variant link. This
is the auditable basis a later promotion resolves the winner from.

Per-window and per-candidate audit detail live in ``optimization_windows`` and
``optimization_trials`` (revision ``0022``): one window row per walk-forward
window (train/test boundaries + the linked OOS ``backtest_runs`` row) and one
trial row per evaluated grid candidate (the multiple-testing record). Windows and
trials are written inside the experiment's ``unit_of_work`` so the whole audit
tree lands atomically.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.backtesting.optimizer_models import (
    ExperimentStatus,
    OptimizationExperimentInsert,
    OptimizationExperimentRecord,
    OptimizationManifestInsert,
    OptimizationManifestRecord,
    OptimizationTrialInsert,
    OptimizationTrialRecord,
    OptimizationWindowInsert,
    OptimizationWindowRecord,
)
from trading.persistence.unit_of_work import commit_unit_of_work

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
            status, failure_stage, failure_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            str(payload.status),
            None if payload.failure_stage is None else str(payload.failure_stage),
            payload.failure_message,
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


def fetch_recent_experiments(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
) -> list[OptimizationExperimentRecord]:
    rows = conn.execute(
        _SELECT + " ORDER BY created_at DESC, id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [OptimizationExperimentRecord.from_mapping(dict(row)) for row in rows]


def fetch_latest_experiment_for_account_strategy(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
) -> OptimizationExperimentRecord | None:
    """Return the most recent completed experiment that is evidence for a strategy.

    An experiment is evidence for a strategy when it either **targeted** it
    (``strategy_id`` — the optimization ran over that strategy, so its per-window
    OOS record measures how optimizing it generalizes) or **produced** it
    (``promoted_strategy_id`` — the winner was minted into this variant, so the
    holdout run used exactly this variant's parameters).

    Failed experiments are excluded: they carry no winner, no ``holdout_run_id``,
    and no window audit, so there is nothing to read evidence from.
    """
    row = conn.execute(
        """
        SELECT e.*
        FROM optimization_experiments e
        LEFT JOIN strategies target ON target.id = e.strategy_id
        LEFT JOIN strategies promoted ON promoted.id = e.promoted_strategy_id
        WHERE e.account_id = ?
          AND e.status = ?
          AND (LOWER(target.strategy_key) = LOWER(?) OR LOWER(promoted.strategy_key) = LOWER(?))
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT 1
        """,
        (int(account_id), str(ExperimentStatus.COMPLETED), strategy_name, strategy_name),
    ).fetchone()
    return OptimizationExperimentRecord.from_mapping(dict(row)) if row is not None else None


def set_promoted_strategy(conn: sqlite3.Connection, *, experiment_id: int, strategy_id: int) -> None:
    """Record the tradeable variant an experiment's winner was promoted into."""
    conn.execute(
        "UPDATE optimization_experiments SET promoted_strategy_id = ? WHERE id = ?",
        (int(strategy_id), int(experiment_id)),
    )
    commit_unit_of_work(conn)


def insert_window(conn: sqlite3.Connection, payload: OptimizationWindowInsert) -> int:
    """Insert one ``optimization_windows`` row and return its id.

    Meant to run inside the experiment's ``unit_of_work`` so it lands atomically
    with the experiment row and the window's trials.
    """
    cursor = conn.execute(
        """
        INSERT INTO optimization_windows (
            experiment_id, window_index, train_start, train_end, test_start, test_end, oos_run_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload.experiment_id),
            int(payload.window_index),
            payload.train_start,
            payload.train_end,
            payload.test_start,
            payload.test_end,
            int(payload.oos_run_id),
        ),
    )
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def insert_trial(conn: sqlite3.Connection, payload: OptimizationTrialInsert) -> int:
    """Insert one ``optimization_trials`` row and return its id.

    Meant to run inside the experiment's ``unit_of_work`` (see :func:`insert_window`).
    """
    cursor = conn.execute(
        """
        INSERT INTO optimization_trials (
            window_id, candidate_index, params_json, params_hash, objective_value,
            annualized_return_pct, max_drawdown_pct, trade_count, eligible,
            rejection_reason, selected
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload.window_id),
            int(payload.candidate_index),
            payload.params_json,
            payload.params_hash,
            payload.objective_value,
            payload.annualized_return_pct,
            float(payload.max_drawdown_pct),
            int(payload.trade_count),
            int(payload.eligible),
            payload.rejection_reason,
            int(payload.selected),
        ),
    )
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def fetch_windows_for_experiment(conn: sqlite3.Connection, *, experiment_id: int) -> list[OptimizationWindowRecord]:
    """Return an experiment's windows in walk-forward (chronological) order."""
    rows = conn.execute(
        "SELECT * FROM optimization_windows WHERE experiment_id = ? ORDER BY window_index ASC",
        (int(experiment_id),),
    ).fetchall()
    return [OptimizationWindowRecord.from_mapping(dict(row)) for row in rows]


def fetch_trials_for_window(conn: sqlite3.Connection, *, window_id: int) -> list[OptimizationTrialRecord]:
    """Return a window's evaluated candidates in canonical candidate order."""
    rows = conn.execute(
        "SELECT * FROM optimization_trials WHERE window_id = ? ORDER BY candidate_index ASC",
        (int(window_id),),
    ).fetchall()
    return [OptimizationTrialRecord.from_mapping(dict(row)) for row in rows]


def fetch_trials_for_experiment(conn: sqlite3.Connection, *, experiment_id: int) -> list[OptimizationTrialRecord]:
    """Return every candidate across an experiment's windows (window then candidate order).

    Reached by join through ``optimization_windows`` — trials carry only ``window_id``,
    so the experiment is resolved via its windows.
    """
    rows = conn.execute(
        """
        SELECT t.*
        FROM optimization_trials t
        JOIN optimization_windows w ON w.id = t.window_id
        WHERE w.experiment_id = ?
        ORDER BY w.window_index ASC, t.candidate_index ASC
        """,
        (int(experiment_id),),
    ).fetchall()
    return [OptimizationTrialRecord.from_mapping(dict(row)) for row in rows]


def insert_manifest(
    conn: sqlite3.Connection, payload: OptimizationManifestInsert, *, created_at: str | None = None
) -> int:
    """Insert one ``optimization_run_manifests`` row and return its id.

    Meant to run inside the experiment's ``unit_of_work`` so the frozen provenance
    snapshot lands atomically with the experiment it describes.
    """
    now = created_at or utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO optimization_run_manifests (
            experiment_id, manifest_version, account_name, book_id, initial_cash,
            benchmark_ticker, slippage_bps, fee_per_trade, effective_execution_json,
            tickers_file, universe_history_dir, universe_tickers_json, universe_size,
            market_data_provider, data_as_of, engine_revision, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload.experiment_id),
            payload.manifest_version,
            payload.account_name,
            payload.book_id if payload.book_id is None else int(payload.book_id),
            float(payload.initial_cash),
            payload.benchmark_ticker,
            float(payload.slippage_bps),
            float(payload.fee_per_trade),
            payload.effective_execution_json,
            payload.tickers_file,
            payload.universe_history_dir,
            payload.universe_tickers_json,
            int(payload.universe_size),
            payload.market_data_provider,
            payload.data_as_of,
            payload.engine_revision,
            now,
        ),
    )
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def fetch_manifest_for_experiment(
    conn: sqlite3.Connection, *, experiment_id: int
) -> OptimizationManifestRecord | None:
    """Return the experiment's frozen provenance manifest, or ``None`` if not stored."""
    row = conn.execute(
        "SELECT * FROM optimization_run_manifests WHERE experiment_id = ?",
        (int(experiment_id),),
    ).fetchone()
    return OptimizationManifestRecord.from_mapping(dict(row)) if row is not None else None
