"""Run strategies through scenarios and collect one outcome distribution per cell.

The runner is pure orchestration. It generates each scenario path once (backtesting
domain), runs every strategy over that same path through an injected ``run_path``
callable, and reduces the per-path results into a :class:`BenchMatrix`. It touches
no database, no market-data adapter, and no files: the composition seam binds
those into ``run_path``. This mirrors how the walk-forward optimizer takes its run
callables, and it keeps the aggregation unit-testable with a fake ``run_path``.
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from backtesting.domain.scenario_bench.aggregation import summarize_cell
from backtesting.domain.scenario_bench.contracts import PathRequest, ScenarioSpec
from backtesting.models.backtest import BACKTEST_PURPOSE_STANDALONE, BacktestConfig, BacktestResult
from backtesting.models.scenario_bench import BenchMatrix, ScenarioCellResult
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.services.accounts.mutations import create_account, get_account

# The synthetic calendar's start. Only the bar count matters for a synthetic run,
# so the anchor is fixed and arbitrary; a fixed anchor keeps a run reproducible.
_ANCHOR_START = date(2000, 1, 3)

# The single reserved account every bench run trades through. Auto-created on
# first use and reused after, so a bench run needs no operator setup and writes no
# per-run account rows.
RESERVED_BENCH_ACCOUNT = "scenario_bench"
# Starting cash for the reserved account. Comfortably above the synthetic prices
# (~100 per share) so position sizing is never cash-starved by the account size.
BENCH_INITIAL_CASH = 100_000.0
# The reserved account needs a valid default-book strategy assignment at creation.
# The bench overrides the strategy on every run, so this assignment is never used.
_BENCH_DEFAULT_STRATEGY = "trend"


@dataclass(frozen=True)
class BenchUniverse:
    """The one universe and benchmark a bench run trades, shared by its scenarios."""

    tickers: tuple[str, ...]
    benchmark: str


def resolve_bench_universe(scenarios: Sequence[ScenarioSpec]) -> BenchUniverse:
    """The shared universe and benchmark of the selected scenarios.

    One run trades one account with one universe file and one benchmark, so every
    scenario in the run must agree on both. Differing scenarios are run separately.
    """
    if not scenarios:
        raise ValidationError("At least one scenario is required.")
    ticker_sets = {spec.tickers for spec in scenarios}
    benchmarks = {spec.benchmark for spec in scenarios}
    if len(ticker_sets) != 1 or len(benchmarks) != 1:
        raise ValidationError(
            "All selected scenarios must share one universe and benchmark; run differing scenarios separately."
        )
    (tickers,) = ticker_sets
    (benchmark,) = benchmarks
    return BenchUniverse(tickers=tickers, benchmark=benchmark)


def ensure_bench_account(conn: sqlite3.Connection, *, benchmark_ticker: str) -> None:
    """Create the reserved bench account if it does not exist, else leave it as is."""
    try:
        get_account(conn, RESERVED_BENCH_ACCOUNT)
    except NotFoundError:
        create_account(
            conn,
            RESERVED_BENCH_ACCOUNT,
            strategy=_BENCH_DEFAULT_STRATEGY,
            initial_cash=BENCH_INITIAL_CASH,
            benchmark_ticker=benchmark_ticker,
        )


def write_synthetic_universe(tickers: Sequence[str]) -> str:
    """Write the synthetic universe to a temporary ticker file and return its path.

    The backtest resolves its universe from a ticker file. The synthetic tickers
    are not real symbols, so the file is temporary and the caller removes it.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="scenario_bench_", delete=False, encoding="utf-8"
    )
    try:
        handle.write("\n".join(tickers) + "\n")
    finally:
        handle.close()
    return handle.name


# A run_path takes one strategy's config and one path's bar-set, and returns the
# simulated result. The composition seam builds the provider and calls the
# metrics-only backtest inside it, so the runner needs neither.
RunPathFn = Callable[[BacktestConfig, Mapping[str, pd.DataFrame]], BacktestResult]


@dataclass(frozen=True)
class BenchRunContext:
    """The run-wide settings the composition seam supplies to every cell."""

    account_name: str
    tickers_file: str
    slippage_bps: float
    fee_per_trade: float


def _build_config(context: BenchRunContext, calendar: pd.DatetimeIndex, strategy: str) -> BacktestConfig:
    return BacktestConfig(
        account_name=context.account_name,
        tickers_file=context.tickers_file,
        universe_history_dir=None,
        start=calendar[0].date().isoformat(),
        end=calendar[-1].date().isoformat(),
        lookback_months=None,
        slippage_bps=context.slippage_bps,
        fee_per_trade=context.fee_per_trade,
        run_name=None,
        allow_approximate_leaps=False,
        strategy=strategy,
        purpose=BACKTEST_PURPOSE_STANDALONE,
        param_override=None,
        warmup_months=0,
    )


def _run_one_scenario(
    spec: ScenarioSpec,
    *,
    strategies: Sequence[str],
    context: BenchRunContext,
    run_path: RunPathFn,
    path_count: int,
) -> list[ScenarioCellResult]:
    calendar = pd.bdate_range(start=_ANCHOR_START, periods=spec.days)
    requested = (*spec.tickers, spec.benchmark)
    configs = {strategy: _build_config(context, calendar, strategy) for strategy in strategies}
    results: dict[str, list[BacktestResult]] = defaultdict(list)

    for path_index in range(path_count):
        # One bar-set per path, shared by every strategy, so the strategies are
        # compared on identical bars and the path is generated once.
        frames = spec.generator(
            PathRequest(
                index=calendar,
                tickers=requested,
                seed=spec.base_seed + path_index,
                params=spec.params,
            )
        )
        for strategy in strategies:
            results[strategy].append(run_path(configs[strategy], frames))

    return [summarize_cell(strategy, spec.scenario_id, results[strategy]) for strategy in strategies]


def run_scenario_bench(
    *,
    strategies: Sequence[str],
    scenarios: Sequence[ScenarioSpec],
    context: BenchRunContext,
    run_path: RunPathFn,
    paths_override: int | None = None,
) -> BenchMatrix:
    """Run every strategy through every scenario and return the outcome grid.

    ``paths_override`` replaces each scenario's own ``path_count`` when set, so the
    caller can trade resolution for speed without editing the catalog.
    """
    strategy_list = list(strategies)
    scenario_ids = [spec.scenario_id for spec in scenarios]
    cells: dict[tuple[str, str], ScenarioCellResult] = {}

    for spec in scenarios:
        path_count = spec.path_count if paths_override is None else max(1, paths_override)
        for cell in _run_one_scenario(
            spec,
            strategies=strategy_list,
            context=context,
            run_path=run_path,
            path_count=path_count,
        ):
            cells[(cell.strategy, cell.scenario_id)] = cell

    return BenchMatrix(strategies=strategy_list, scenario_ids=scenario_ids, cells=cells)


# Width of one scenario column in the rendered matrix.
_COLUMN_WIDTH = 22


def _format_cell(cell: ScenarioCellResult, metric: str) -> str:
    dist = cell.distributions.get(metric)
    if dist is None or dist.p50 is None or dist.p5 is None:
        return "n/a"
    return f"{dist.p50:+.1f} (p5 {dist.p5:+.1f})"


def render_bench_matrix(matrix: BenchMatrix, *, metric: str = "total_return_pct") -> str:
    """A text grid of one metric's median and 5th-percentile value per cell.

    Rows are strategies, columns are scenarios. Each cell shows the metric's median
    across the scenario's paths and, in parentheses, its 5th-percentile downside.
    """
    label_width = max((len(strategy) for strategy in matrix.strategies), default=0)
    label_width = max(label_width, len("strategy"))

    header = (
        "strategy".ljust(label_width)
        + "  "
        + "".join(scenario_id[:_COLUMN_WIDTH].ljust(_COLUMN_WIDTH) for scenario_id in matrix.scenario_ids)
    )
    lines = [f"metric: {metric} - median (5th-percentile downside)", header]
    for strategy in matrix.strategies:
        row = (
            strategy.ljust(label_width)
            + "  "
            + "".join(
                _format_cell(matrix.cell(strategy, scenario_id), metric).ljust(_COLUMN_WIDTH)
                for scenario_id in matrix.scenario_ids
            )
        )
        lines.append(row)
    return "\n".join(lines)
