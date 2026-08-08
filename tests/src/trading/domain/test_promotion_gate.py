"""Promotion quality gate (pure domain logic): OOS mean, OOS majority, and holdout
comparisons against the strategy's own default."""

from __future__ import annotations

from trading.domain.promotion_gate import evaluate_promotion_gate


def _gate(
    *,
    oos_mean_winner_return_pct=1.0,
    oos_mean_baseline_return_pct=0.5,
    oos_windows_beat_baseline=3,
    window_count=4,
    holdout_winner_return_pct=2.0,
    holdout_baseline_return_pct=1.0,
):
    return evaluate_promotion_gate(
        oos_mean_winner_return_pct=oos_mean_winner_return_pct,
        oos_mean_baseline_return_pct=oos_mean_baseline_return_pct,
        oos_windows_beat_baseline=oos_windows_beat_baseline,
        window_count=window_count,
        holdout_winner_return_pct=holdout_winner_return_pct,
        holdout_baseline_return_pct=holdout_baseline_return_pct,
    )


class TestEvaluatePromotionGate:
    def test_passes_when_winner_beats_default_on_every_measure(self) -> None:
        result = _gate()
        assert result.passed
        assert result.reasons == ()

    def test_fails_when_oos_mean_does_not_beat_baseline(self) -> None:
        result = _gate(oos_mean_winner_return_pct=0.5, oos_mean_baseline_return_pct=1.0)
        assert not result.passed
        assert any("OOS mean return" in reason for reason in result.reasons)

    def test_oos_mean_tie_fails_not_passes(self) -> None:
        # Strictly greater-than: a tie is not a win.
        result = _gate(oos_mean_winner_return_pct=1.0, oos_mean_baseline_return_pct=1.0)
        assert not result.passed

    def test_fails_when_oos_window_win_rate_is_not_a_majority(self) -> None:
        # A good mean can mask a coin-flip per-window record.
        result = _gate(oos_windows_beat_baseline=2, window_count=4)
        assert not result.passed
        assert any("2/4 OOS windows" in reason for reason in result.reasons)

    def test_oos_window_win_rate_exact_half_fails(self) -> None:
        # Strict majority required: exactly half does not clear the bar.
        result = _gate(oos_windows_beat_baseline=2, window_count=4, oos_mean_winner_return_pct=5.0)
        assert not result.passed

    def test_fails_when_holdout_does_not_beat_baseline(self) -> None:
        result = _gate(holdout_winner_return_pct=1.0, holdout_baseline_return_pct=2.0)
        assert not result.passed
        assert any("holdout return" in reason for reason in result.reasons)

    def test_missing_oos_mean_evidence_fails(self) -> None:
        result = _gate(oos_mean_winner_return_pct=None)
        assert not result.passed
        assert any("no OOS mean-return evidence" in reason for reason in result.reasons)

    def test_missing_oos_window_evidence_fails(self) -> None:
        result = _gate(oos_windows_beat_baseline=None)
        assert not result.passed
        assert any("no per-window OOS evidence" in reason for reason in result.reasons)

    def test_zero_windows_counts_as_missing_oos_window_evidence(self) -> None:
        result = _gate(window_count=0)
        assert not result.passed
        assert any("no per-window OOS evidence" in reason for reason in result.reasons)

    def test_missing_holdout_evidence_fails(self) -> None:
        result = _gate(holdout_winner_return_pct=None, holdout_baseline_return_pct=None)
        assert not result.passed
        assert any("no holdout evidence" in reason for reason in result.reasons)

    def test_every_failure_reason_is_reported_not_just_the_first(self) -> None:
        result = _gate(
            oos_mean_winner_return_pct=None,
            oos_windows_beat_baseline=None,
            holdout_winner_return_pct=None,
            holdout_baseline_return_pct=None,
        )
        assert not result.passed
        assert len(result.reasons) == 3
