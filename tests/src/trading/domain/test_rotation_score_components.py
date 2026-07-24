from __future__ import annotations

import pytest

from trading.domain.rotation.score_components import (
    NEUTRAL_COMPONENT,
    drawdown_penalty_from_max_drawdown,
    stability_from_window_returns,
)


class TestStabilityFromWindowReturns:
    def test_tight_windows_score_near_zero(self) -> None:
        steady = stability_from_window_returns(best_return_pct=4.2, worst_return_pct=3.8, window_count=5)
        assert steady == pytest.approx(-0.4)

    def test_wider_spread_scores_lower(self) -> None:
        steady = stability_from_window_returns(best_return_pct=4.2, worst_return_pct=3.8, window_count=5)
        swingy = stability_from_window_returns(best_return_pct=12.0, worst_return_pct=-8.0, window_count=5)
        # Stability is added to the score, so the steadier strategy must rank higher.
        assert swingy < steady

    def test_single_window_is_neutral_not_perfectly_stable(self) -> None:
        # One window has zero spread, which would otherwise read as flawless steadiness.
        assert stability_from_window_returns(best_return_pct=4.0, worst_return_pct=4.0, window_count=1) == (
            NEUTRAL_COMPONENT
        )

    def test_missing_window_returns_are_neutral(self) -> None:
        assert stability_from_window_returns(best_return_pct=None, worst_return_pct=1.0, window_count=4) == (
            NEUTRAL_COMPONENT
        )
        assert stability_from_window_returns(best_return_pct=1.0, worst_return_pct=None, window_count=4) == (
            NEUTRAL_COMPONENT
        )

    def test_identical_windows_are_maximally_steady(self) -> None:
        assert stability_from_window_returns(best_return_pct=3.0, worst_return_pct=3.0, window_count=4) == 0.0

    def test_never_returns_a_positive_bonus(self) -> None:
        # Stability may only be neutral or negative; a positive value would reward
        # dispersion once the policy adds it to the score.
        assert stability_from_window_returns(best_return_pct=9.0, worst_return_pct=1.0, window_count=3) <= 0.0


class TestDrawdownPenaltyFromMaxDrawdown:
    def test_negative_drawdown_becomes_positive_magnitude(self) -> None:
        # The policy SUBTRACTS this component, so a 12% decline must yield +12.0.
        # Passing the stored negative through unchanged would raise the score instead.
        assert drawdown_penalty_from_max_drawdown(-12.0) == pytest.approx(12.0)

    def test_deeper_drawdown_penalizes_more(self) -> None:
        assert drawdown_penalty_from_max_drawdown(-20.0) > drawdown_penalty_from_max_drawdown(-5.0)

    def test_no_drawdown_is_neutral(self) -> None:
        assert drawdown_penalty_from_max_drawdown(0.0) == NEUTRAL_COMPONENT

    def test_missing_drawdown_is_neutral(self) -> None:
        assert drawdown_penalty_from_max_drawdown(None) == NEUTRAL_COMPONENT
