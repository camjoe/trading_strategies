"""Time the walk-forward optimizer so sweep sizing can be chosen from data.

A sweep is ``candidates x windows`` training backtests plus a persisted OOS run
and a metrics-only baseline per window, plus two holdout runs. The route's
candidate-budget ceiling is derived from what one simulation costs, so re-run
this whenever the inner loop changes and re-derive the cap from the result.

Runs against a *copy* of the database (SQLite backup API, so WAL content comes
along), because a sweep persists its OOS and holdout runs and a benchmark should
not leave evidence rows behind.

    python -m scripts.benchmark_sweep --account momentum_5k --label baseline

Add ``--json-out local/sweep_benchmarks.jsonl`` to append a machine-readable row
per run for before/after comparison.

**Read the output with suspicion.** One run is one sample, and repeated runs of
an identical configuration have come in 23% apart on the same machine. A single
before/after pair therefore cannot resolve anything below roughly 25%. For a
smaller effect, profile where the time goes rather than A/B timing the whole
sweep — or teach this script to interleave repeated trials and report the
minimum, since noise only ever adds time.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import date
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backtesting.composition import run_backtest, run_backtest_metrics_only
from backtesting.domain.optimization.search import generate_candidates
from backtesting.domain.windowing import build_walk_forward_optimization_splits, resolve_run_window
from backtesting.models import BACKTEST_PURPOSE_STANDALONE, BacktestConfig
from backtesting.models.optimizer import OptimizerConfig
from backtesting.services.walk_forward_optimizer_service import run_walk_forward_optimization
from infrastructure.database.backend import SQLiteBackend, set_backend
from infrastructure.database.config import get_db_path
from infrastructure.market_data.factory import build_provider
from trading.services.market_data import MarketDataProvider
from trading.services.universe import DEFAULT_TICKERS_FILE

# An 8-point grid over a two-parameter strategy: small enough to finish while
# someone watches, large enough that per-candidate setup cost is visible.
DEFAULT_SEARCH_SPACE = '{"fast_window": [5, 10, 15, 20], "slow_window": [40, 60]}'

# 30 months of lookback with the default 12/1/1/6 geometry yields 12 windows —
# the "8 candidates x 12 windows" shape the work plan asks to confirm.
DEFAULT_LOOKBACK_MONTHS = 30


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", required=True, help="Account name to benchmark against.")
    parser.add_argument("--strategy", default="ma_crossover")
    parser.add_argument("--search-space", default=DEFAULT_SEARCH_SPACE, help="JSON parameter grid.")
    parser.add_argument("--tickers-file", default=DEFAULT_TICKERS_FILE)
    parser.add_argument("--universe-history-dir", default=None)
    parser.add_argument("--lookback-months", type=int, default=DEFAULT_LOOKBACK_MONTHS)
    parser.add_argument("--train-months", type=int, default=12)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--holdout-months", type=int, default=6)
    parser.add_argument("--warmup-months", type=int, default=6)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--db", default=None, help="Source database to copy (default: the configured path).")
    parser.add_argument("--label", default="run", help="Tag recorded with the result row.")
    parser.add_argument("--json-out", default=None, help="Append one JSON result line to this file.")
    parser.add_argument("--skip-single", action="store_true", help="Skip the single-backtest measurement.")
    parser.add_argument("--skip-sweep", action="store_true", help="Skip the full-sweep measurement.")
    return parser.parse_args()


def _grid_size(search_space: dict[str, list[Any]]) -> int:
    """Number of points in the full cartesian grid.

    ``generate_candidates`` rejects a grid larger than its budget, so the
    benchmark hands it the grid's own size — the benchmark measures whatever
    grid it was given rather than sampling a subset of it.
    """
    size = 1
    for values in search_space.values():
        size *= len(values)
    return size


def _copy_database(source: Path, destination: Path) -> None:
    """Copy *source* to *destination* through SQLite's backup API.

    A plain file copy can miss commits still living in the -wal sidecar; the
    backup API always produces a consistent snapshot. Both handles are closed
    explicitly — on Windows an open handle blocks the temp directory cleanup.
    """
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _optimizer_config(args: argparse.Namespace, search_space: dict[str, list[Any]]) -> OptimizerConfig:
    return OptimizerConfig(
        account_name=args.account,
        tickers_file=args.tickers_file,
        universe_history_dir=args.universe_history_dir,
        strategy=args.strategy,
        search_space=search_space,
        start=None,
        end=None,
        lookback_months=args.lookback_months,
        slippage_bps=args.slippage_bps,
        fee_per_trade=args.fee,
        allow_approximate_leaps=False,
        train_months=args.train_months,
        test_months=args.test_months,
        step_months=args.step_months,
        holdout_months=args.holdout_months,
        candidate_budget=_grid_size(search_space),
        warmup_months=args.warmup_months,
    )


def _time_single_backtest(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    provider: MarketDataProvider,
    train_start: date,
    train_end: date,
    params: dict[str, Any],
) -> float:
    """Return seconds for one metrics-only candidate backtest over a training window."""
    started = time.perf_counter()
    run_backtest_metrics_only(
        conn,
        BacktestConfig(
            account_name=cfg.account_name,
            tickers_file=cfg.tickers_file,
            universe_history_dir=cfg.universe_history_dir,
            start=train_start.isoformat(),
            end=train_end.isoformat(),
            lookback_months=None,
            slippage_bps=cfg.slippage_bps,
            fee_per_trade=cfg.fee_per_trade,
            run_name=None,
            allow_approximate_leaps=cfg.allow_approximate_leaps,
            strategy=cfg.strategy,
            purpose=BACKTEST_PURPOSE_STANDALONE,
            param_override=params,
            warmup_months=cfg.warmup_months,
        ),
    )
    return time.perf_counter() - started


def main() -> None:
    args = _parse_args()
    search_space = json.loads(args.search_space)
    if not isinstance(search_space, dict):
        raise SystemExit("--search-space must be a JSON object mapping parameter -> list of values")

    cfg = _optimizer_config(args, search_space)
    candidates = generate_candidates(search_space, budget=cfg.candidate_budget)
    start_date, end_date = resolve_run_window(cfg.start, cfg.end, cfg.lookback_months)
    splits, holdout = build_walk_forward_optimization_splits(
        start_date,
        end_date,
        train_months=cfg.train_months,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        holdout_months=cfg.holdout_months,
    )

    # Training trials dominate; the rest is one persisted OOS + one metrics-only
    # baseline per window, plus the same pair once for the holdout.
    training_runs = len(candidates) * len(splits)
    supporting_runs = 2 * len(splits) + (2 if holdout is not None else 0)

    print(f"account={cfg.account_name} strategy={cfg.strategy} label={args.label}")
    print(f"span={start_date}..{end_date} candidates={len(candidates)} windows={len(splits)}")
    print(f"simulations: {training_runs} training + {supporting_runs} supporting = {training_runs + supporting_runs}")

    source_db = Path(args.db) if args.db else get_db_path()
    result: dict[str, Any] = {
        "label": args.label,
        "account": cfg.account_name,
        "strategy": cfg.strategy,
        "tickers_file": cfg.tickers_file,
        "candidates": len(candidates),
        "windows": len(splits),
        "training_runs": training_runs,
        "supporting_runs": supporting_runs,
    }

    with TemporaryDirectory(prefix="sweep_benchmark_") as tmp:
        working_db = Path(tmp) / "benchmark.db"
        _copy_database(source_db, working_db)
        set_backend(SQLiteBackend(db_path=working_db))
        conn = sqlite3.connect(working_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # One provider for the whole benchmark, so the timings measure simulation
        # cost rather than repeated adapter construction.
        provider = build_provider()
        try:
            if not args.skip_single:
                first = splits[0]
                # Two timings: the first pays whatever the process has not warmed
                # (imports, cache reads), the second is the steady-state cost that
                # every later candidate in a window actually pays.
                cold = _time_single_backtest(
                    conn,
                    cfg,
                    provider=provider,
                    train_start=first.train_start,
                    train_end=first.train_end,
                    params=candidates[0],
                )
                warm = _time_single_backtest(
                    conn,
                    cfg,
                    provider=provider,
                    train_start=first.train_start,
                    train_end=first.train_end,
                    params=candidates[-1],
                )
                result["single_cold_seconds"] = round(cold, 4)
                result["single_warm_seconds"] = round(warm, 4)
                print(f"single backtest: cold {cold:.3f}s, warm {warm:.3f}s")
                print(f"linear model for the sweep: {(training_runs + supporting_runs) * warm:.1f}s")

            if not args.skip_sweep:
                started = time.perf_counter()
                summary = run_walk_forward_optimization(
                    conn,
                    cfg,
                    run_metrics_only_fn=partial(run_backtest_metrics_only, provider=provider),
                    run_persisted_fn=partial(run_backtest, provider=provider),
                )
                elapsed = time.perf_counter() - started
                total_runs = training_runs + supporting_runs
                result["sweep_seconds"] = round(elapsed, 4)
                result["sweep_seconds_per_simulation"] = round(elapsed / total_runs, 4)
                result["sweep_windows_completed"] = len(summary.windows)
                print(
                    f"full sweep: {elapsed:.2f}s over {total_runs} simulations "
                    f"({elapsed / total_runs * 1000:.1f} ms each)"
                )
        finally:
            conn.close()

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
        print(f"appended result to {out_path}")


if __name__ == "__main__":
    main()
