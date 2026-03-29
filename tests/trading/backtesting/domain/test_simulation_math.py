from __future__ import annotations

import pytest

from trading.backtesting.domain.simulation_math import compute_market_value, compute_unrealized_pnl


def test_market_value_and_unrealized_pnl_ignore_missing_or_non_positive_positions() -> None:
    positions = {"AAPL": 2.0, "MSFT": 1.5, "NVDA": 0.0}
    prices = {"AAPL": 10.0, "MSFT": 20.0}
    avg_cost = {"AAPL": 8.0, "MSFT": 25.0, "NVDA": 100.0}

    assert compute_market_value(positions, prices) == pytest.approx(50.0)
    assert compute_unrealized_pnl(positions, avg_cost, prices) == pytest.approx(-3.5)