"""Passive data contracts for the backtesting context, in feature modules.

Three areas, one module each: `backtest` for a run's config and result, `optimizer`
for the walk-forward search and everything it persists, `report` for the shapes
operator surfaces read. The package root re-exports the stable public types, the
same arrangement `trading.models` uses.

Distinct from `trading.models`, which holds the contracts for the tables
`trading/repositories/` owns. These belong to the seven tables this context owns —
see [ADR 005](../../../docs/adr/005-models-as-lowest-data-layer.md) for why that
split is deliberate rather than drift.
"""

from __future__ import annotations

from backtesting.models.backtest import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
)

__all__ = [
    "BACKTEST_PURPOSE_FINAL_HOLDOUT",
    "BACKTEST_PURPOSE_STANDALONE",
    "BACKTEST_PURPOSE_WALK_FORWARD_OOS",
    "BacktestBatchConfig",
    "BacktestConfig",
    "BacktestResult",
]
