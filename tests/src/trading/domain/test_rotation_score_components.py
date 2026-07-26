from __future__ import annotations

import pytest

from trading.domain.feature_provider import POLICY_RISK_OFF_SELL_THRESHOLD, POLICY_RISK_ON_BUY_THRESHOLD
from trading.domain.rotation.score_components import (
    NEUTRAL_COMPONENT,
    REGIME_FIT_MATCH_BONUS_PCT,
    MarketRegime,
    drawdown_penalty_from_max_drawdown,
    regime_bucket_from_risk_on_score,
    regime_fit_from_style,
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


class TestRegimeBucketFromRiskOnScore:
    def test_above_buy_threshold_is_risk_on(self) -> None:
        assert regime_bucket_from_risk_on_score(POLICY_RISK_ON_BUY_THRESHOLD + 0.01) == MarketRegime.RISK_ON

    def test_below_sell_threshold_is_risk_off(self) -> None:
        assert regime_bucket_from_risk_on_score(POLICY_RISK_OFF_SELL_THRESHOLD - 0.01) == MarketRegime.RISK_OFF

    def test_between_thresholds_is_neutral(self) -> None:
        midpoint = (POLICY_RISK_ON_BUY_THRESHOLD + POLICY_RISK_OFF_SELL_THRESHOLD) / 2
        assert regime_bucket_from_risk_on_score(midpoint) == MarketRegime.NEUTRAL

    def test_missing_score_is_none_not_neutral(self) -> None:
        # None means "unavailable" (a failed/stale live fetch); the caller must
        # treat it the same as no match, but it is a distinct value from an
        # actually-observed neutral regime.
        assert regime_bucket_from_risk_on_score(None) is None


class TestRegimeFitFromStyle:
    def test_matching_affinity_awards_bonus(self) -> None:
        assert (
            regime_fit_from_style(strategy_style="trend", current_regime=MarketRegime.RISK_ON)
            == REGIME_FIT_MATCH_BONUS_PCT
        )
        assert (
            regime_fit_from_style(strategy_style="mean_reversion", current_regime=MarketRegime.RISK_OFF)
            == REGIME_FIT_MATCH_BONUS_PCT
        )

    def test_mismatch_is_neutral_not_penalized(self) -> None:
        # A strategy is never punished for its style, only optionally rewarded.
        assert regime_fit_from_style(strategy_style="trend", current_regime=MarketRegime.RISK_OFF) == NEUTRAL_COMPONENT

    def test_neutral_regime_is_neutral(self) -> None:
        assert regime_fit_from_style(strategy_style="trend", current_regime=MarketRegime.NEUTRAL) == NEUTRAL_COMPONENT

    def test_unavailable_regime_is_neutral(self) -> None:
        assert regime_fit_from_style(strategy_style="trend", current_regime=None) == NEUTRAL_COMPONENT

    def test_unmapped_style_is_neutral(self) -> None:
        assert (
            regime_fit_from_style(strategy_style="alternative", current_regime=MarketRegime.RISK_ON)
            == NEUTRAL_COMPONENT
        )
        assert regime_fit_from_style(strategy_style=None, current_regime=MarketRegime.RISK_ON) == NEUTRAL_COMPONENT
