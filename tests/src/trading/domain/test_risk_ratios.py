from __future__ import annotations

import pytest

from common.constants import ANNUALIZATION_FACTOR
from trading.domain.metrics.risk_ratios import sharpe_ratio


class TestSharpeRatio:
    def test_scores_a_series_with_dispersion(self) -> None:
        assert sharpe_ratio([0.01, -0.005, 0.02, -0.01]) == pytest.approx(4.9923017660270625)

    def test_empty_series_has_no_ratio(self) -> None:
        assert sharpe_ratio([]) is None

    def test_flat_series_has_no_ratio(self) -> None:
        # Zero volatility makes the ratio undefined rather than infinite.
        assert sharpe_ratio([0.01, 0.01, 0.01]) is None

    def test_single_return_has_no_dispersion(self) -> None:
        assert sharpe_ratio([0.02]) is None

    def test_uses_population_standard_deviation(self) -> None:
        # ddof=0, so a two-point series has std = half the gap, not the full gap.
        # mean 0.015, population std 0.005 -> 3.0 before annualizing.
        assert sharpe_ratio([0.01, 0.02]) == pytest.approx(3.0 * ANNUALIZATION_FACTOR)

    def test_risk_free_rate_lowers_the_ratio(self) -> None:
        returns = [0.01, -0.005, 0.02, -0.01]
        assert sharpe_ratio(returns, risk_free_rate=0.05) < sharpe_ratio(returns)
