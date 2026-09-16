from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace

import pandas as pd

from backtesting.domain.scenario_bench.contracts import (
    SCENARIO_MODE_BOOTSTRAP,
    SCENARIO_MODE_REPLAY,
    PathRequest,
    ScenarioSpec,
)
from backtesting.domain.scenario_bench.generators import bootstrap_frames, replay_frames
from backtesting.models import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
)
from backtesting.models.scenario_bench import BenchMatrix
from backtesting.services.run_inputs import fetch_bar_history, fetch_benchmark_close
from backtesting.services.scenario_bench import (
    RESERVED_BENCH_ACCOUNT,
    BenchRunContext,
    ensure_bench_account,
    resolve_bench_universe,
    run_scenario_bench,
    write_synthetic_universe,
)
from backtesting.services.scenario_fixtures import load_fixture
from backtesting.services.simulation import run_backtest as run_backtest_impl
from infrastructure.market_data.scenario_provider import ScenarioMarketDataProvider
from trading.domain.exceptions import ValidationError
from trading.services.market_data.factory import build_feature_provider
from trading.services.market_data.protocols import MarketDataProvider


def _run_backtest(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
    persist: bool,
) -> BacktestResult:
    # Binds one caller-supplied provider into the run's data path, so no service
    # below reaches for a provider itself.
    feature_provider = build_feature_provider(market_data_provider=provider)
    return run_backtest_impl(
        conn,
        cfg,
        fetch_bar_history_fn=lambda tickers, start_date, end_date: fetch_bar_history(
            tickers, start_date, end_date, provider=provider
        ),
        fetch_benchmark_close_fn=lambda benchmark_ticker, start_date, end_date: fetch_benchmark_close(
            benchmark_ticker, start_date, end_date, provider=provider
        ),
        persist=persist,
        feature_provider=feature_provider,
    )


def run_backtest(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
) -> BacktestResult:
    """Run one backtest against *provider* and persist it.

    The provider is supplied, never built here: the application entrypoint builds
    one per invocation. A provider carries per-instance call guards (the yfinance
    adapter's rate limiter caps cumulative calls for its own lifetime), so
    building one per run would reset those guards on every run — and an optimizer
    sweep runs one backtest per candidate per window.
    """
    return _run_backtest(conn, cfg, provider=provider, persist=True)


def run_backtest_metrics_only(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
) -> BacktestResult:
    """Run a simulation and return its metrics without persisting any run, trade, or
    snapshot rows. Lets the walk-forward optimizer evaluate grid candidates on training
    windows without polluting stored backtest evidence."""
    return _run_backtest(conn, cfg, provider=provider, persist=False)


def run_backtest_batch(
    conn: sqlite3.Connection,
    cfg: BacktestBatchConfig,
    *,
    provider: MarketDataProvider,
) -> list[BacktestResult]:
    account_names = [name.strip() for name in cfg.account_names if name.strip()]
    if not account_names:
        raise ValueError("At least one account name is required.")

    results: list[BacktestResult] = []
    for idx, account_name in enumerate(account_names, start=1):
        run_name = None
        if cfg.run_name_prefix:
            run_name = f"{cfg.run_name_prefix}_{idx:02d}_{account_name}"

        result = run_backtest(
            conn,
            BacktestConfig(
                account_name=account_name,
                tickers_file=cfg.tickers_file,
                universe_history_dir=cfg.universe_history_dir,
                start=cfg.start,
                end=cfg.end,
                lookback_months=cfg.lookback_months,
                slippage_bps=cfg.slippage_bps,
                fee_per_trade=cfg.fee_per_trade,
                run_name=run_name,
                allow_approximate_leaps=cfg.allow_approximate_leaps,
            ),
            provider=provider,
        )
        results.append(result)

    results.sort(key=lambda item: item.total_return_pct, reverse=True)
    return results


def _bind_scenario(spec: ScenarioSpec) -> ScenarioSpec:
    """Bind a real-data scenario to its loaded fixture, or pass a synthetic one through.

    A real-data scenario carries a `FixtureSource` and the unbound generator
    sentinel. This loads the fixture (the only file read) and replaces the
    generator with a replay or bootstrap closure over the real bars. Replay also
    takes its length from the fixture, so `days` is overridden with the real count.
    """
    source = spec.source
    if source is None:
        return spec

    bars = load_fixture(source.fixture_id)
    if source.mode == SCENARIO_MODE_REPLAY:
        length = min(len(frame) for frame in bars.values())

        def replay_generator(request: PathRequest) -> dict[str, pd.DataFrame]:
            return replay_frames(bars, request.tickers, request.index)

        return replace(spec, generator=replay_generator, days=length, source=None)

    if source.mode == SCENARIO_MODE_BOOTSTRAP:
        block_size = source.block_size

        def bootstrap_generator(request: PathRequest) -> dict[str, pd.DataFrame]:
            return bootstrap_frames(bars, request.tickers, request.index, request.seed, block_size)

        return replace(spec, generator=bootstrap_generator, source=None)

    raise ValidationError(f"Unknown scenario source mode '{source.mode}'.")


def run_bench(
    conn: sqlite3.Connection,
    *,
    strategy_names: Sequence[str],
    scenario_specs: Sequence[ScenarioSpec],
    paths_override: int | None,
    slippage_bps: float,
    fee_per_trade: float,
) -> BenchMatrix:
    """Run strategies through scenarios and return the outcome grid.

    This is the bench composition seam: it binds real-data scenarios to their
    fixtures, builds a fresh ``ScenarioMarketDataProvider`` per generated path, and
    runs each cell through the metrics-only backtest, so no run, trade, or snapshot
    row is persisted — a behavioral bench is not promotion evidence. The reserved
    bench account is created on first use and pointed at the run's benchmark.
    """
    universe = resolve_bench_universe(scenario_specs)
    ensure_bench_account(conn, benchmark_ticker=universe.benchmark)
    tickers_file = write_synthetic_universe(universe.tickers)
    bound_specs = [_bind_scenario(spec) for spec in scenario_specs]
    context = BenchRunContext(
        account_name=RESERVED_BENCH_ACCOUNT,
        tickers_file=tickers_file,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
    )

    def run_path(cfg: BacktestConfig, frames: Mapping[str, pd.DataFrame]) -> BacktestResult:
        return run_backtest_metrics_only(conn, cfg, provider=ScenarioMarketDataProvider(frames))

    try:
        return run_scenario_bench(
            strategies=strategy_names,
            scenarios=bound_specs,
            context=context,
            run_path=run_path,
            paths_override=paths_override,
        )
    finally:
        os.unlink(tickers_file)
