"""End-to-end test for the data-defined strategy-variant CLI commands.

Covers the core capability "data-defined strategy variants" from
``docs/overview.md``: an operator creates a variant of a code primitive, tunes
its knobs, and freezes it — all as data, with no deploy. The assertion reads
the catalog row the three commands wrote.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from infrastructure.database.connection import ensure_db
from trading.repositories.strategies import StrategyRepository


def test_strategy_variant_lifecycle_via_cli(run_cli: Callable[..., str]) -> None:
    created = run_cli(
        "create-strategy-variant",
        "--strategy",
        "ma_fast_pilot",
        "--primitive",
        "ma_crossover",
        "--set",
        "fast_window=10",
        "--set",
        "slow_window=30",
    )
    assert "Created strategy ma_fast_pilot" in created

    run_cli("configure-strategy", "--strategy", "ma_fast_pilot", "--set", "fast_window=12")
    frozen = run_cli("freeze-strategy", "--strategy", "ma_fast_pilot")
    assert "status=frozen" in frozen

    verify = ensure_db()
    try:
        record = StrategyRepository(verify).fetch_by_key(strategy_key="ma_fast_pilot")
    finally:
        verify.close()

    assert record is not None
    assert record.primitive == "ma_crossover"
    assert record.status == "frozen"
    params = json.loads(record.params_json)
    assert int(params["fast_window"]) == 12
    assert int(params["slow_window"]) == 30
