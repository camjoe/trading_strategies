"""Test helpers for strategy identity and signal evaluation.

``ensure_strategy_id_for_label`` resolves a strategy label to a strategies-row id:
backtest tables key the strategy as a ``strategy_id`` FK, so tests that raw-insert
backtest runs use this to obtain a valid id, draft-creating a catalog row when the
strategy catalog has not been seeded in the fixture.

``signal_with_default_params`` evaluates a signal without the caller stating params.
Production always carries resolved params (the catalog row's knobs), so no runtime
path wants this — only tests asserting a primitive's out-of-the-box behaviour.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from common.time import utc_now_iso
from trading.domain.strategies.resolution import evaluate_signal_over_bars, resolve_strategy
from trading.repositories.strategies import StrategyRepository


def ensure_strategy_id_for_label(conn: sqlite3.Connection, label: str, *, now_iso: str | None = None) -> int:
    strategy_id = StrategyRepository(conn).ensure_id_for_label(label=label, now_iso=now_iso or utc_now_iso())
    assert strategy_id is not None  # non-empty label always resolves or draft-creates
    return strategy_id


def signal_with_default_params(
    strategy_name: str,
    bars: pd.DataFrame,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Evaluate a strategy's signal over ``bars`` using its registered default params."""
    spec = resolve_strategy(strategy_name)
    return evaluate_signal_over_bars(strategy_name, bars, spec.default_params, feature_history)
