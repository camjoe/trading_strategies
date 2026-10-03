"""Tests for trading.services.analysis.calculations."""

from __future__ import annotations

import pytest

from trading.models import AccountState
from trading.services.analysis.position import (
    ALPHA_COMMENT_THRESHOLD_PCT,
    CONCENTRATION_THRESHOLD_PCT,
    compute_position_analysis,
    generate_improvement_notes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(positions: dict[str, float], avg_cost: dict[str, float] | None = None) -> AccountState:
    return AccountState(positions=positions, avg_cost=avg_cost or {}, cash=0.0, realized_pnl=0.0)


# ---------------------------------------------------------------------------
# compute_position_analysis
# ---------------------------------------------------------------------------


class TestComputePositionAnalysis:
    def test_positive_qty_included(self) -> None:
        state = _state({"AAPL": 10.0}, {"AAPL": 100.0})
        result = compute_position_analysis(state, {"AAPL": 110.0}, total_equity=2000.0)
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"

    def test_zero_qty_excluded(self) -> None:
        """qty <= 0 → skip (line 32)."""
        state = _state({"AAPL": 0.0, "MSFT": 5.0}, {"MSFT": 200.0})
        result = compute_position_analysis(state, {"AAPL": 100.0, "MSFT": 210.0}, total_equity=2000.0)
        tickers = [r["ticker"] for r in result]
        assert "AAPL" not in tickers
        assert "MSFT" in tickers

    def test_negative_qty_excluded(self) -> None:
        state = _state({"AAPL": -1.0})
        result = compute_position_analysis(state, {"AAPL": 100.0}, total_equity=1000.0)
        assert result == []

    def test_missing_price_gives_zero_market_value(self) -> None:
        state = _state({"AAPL": 5.0}, {"AAPL": 100.0})
        result = compute_position_analysis(state, {}, total_equity=500.0)
        assert result[0]["market_value"] == 0.0
        assert result[0]["unrealized_pnl"] == 0.0

    def test_portfolio_pct_computed(self) -> None:
        state = _state({"AAPL": 10.0}, {"AAPL": 100.0})
        result = compute_position_analysis(state, {"AAPL": 100.0}, total_equity=1000.0)
        assert result[0]["portfolio_pct"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# generate_improvement_notes
# ---------------------------------------------------------------------------


class TestGenerateImprovementNotes:
    def _positions(self, portfolio_pct: float = 10.0) -> list[dict]:
        return [
            {
                "ticker": "AAPL",
                "portfolio_pct": portfolio_pct,
                "market_price": 100.0,
                "unrealized_pnl_pct": 5.0,
            }
        ]

    def test_trailing_benchmark_note_when_alpha_negative(self) -> None:
        """alpha < -threshold → underperformance note (lines 72-76)."""
        notes = generate_improvement_notes(
            account_return_pct=2.0,
            benchmark_return_pct=10.0,
            alpha=-(ALPHA_COMMENT_THRESHOLD_PCT + 1.0),
            position_analysis=self._positions(),
            realized_pnl=0.0,
        )
        assert any("trailing" in n.lower() or "consider" in n.lower() for n in notes)

    def test_outperforming_note_when_alpha_positive(self) -> None:
        """alpha > threshold → outperforming note (lines 77-80)."""
        notes = generate_improvement_notes(
            account_return_pct=15.0,
            benchmark_return_pct=5.0,
            alpha=ALPHA_COMMENT_THRESHOLD_PCT + 1.0,
            position_analysis=self._positions(),
            realized_pnl=0.0,
        )
        assert any("outperform" in n.lower() for n in notes)

    def test_in_line_note_when_alpha_neutral(self) -> None:
        """alpha within threshold → roughly-in-line note (lines 81-84)."""
        notes = generate_improvement_notes(
            account_return_pct=5.0,
            benchmark_return_pct=5.0,
            alpha=0.0,
            position_analysis=self._positions(),
            realized_pnl=0.0,
        )
        assert any("line" in n.lower() for n in notes)

    def test_no_benchmark_note_when_benchmark_none(self) -> None:
        notes = generate_improvement_notes(
            account_return_pct=5.0,
            benchmark_return_pct=None,
            alpha=None,
            position_analysis=self._positions(),
            realized_pnl=0.0,
        )
        # Should not include benchmark comparison note
        assert not any("benchmark" in n.lower() for n in notes)

    def test_concentration_note_when_single_position_dominates(self) -> None:
        """Position > CONCENTRATION_THRESHOLD_PCT → concentration note (lines 86-92)."""
        notes = generate_improvement_notes(
            account_return_pct=0.0,
            benchmark_return_pct=None,
            alpha=None,
            position_analysis=self._positions(portfolio_pct=CONCENTRATION_THRESHOLD_PCT + 5.0),
            realized_pnl=0.0,
        )
        assert any("concentration" in n.lower() or "exceed" in n.lower() for n in notes)

    def test_realized_loss_note(self) -> None:
        """realized_pnl < 0 → realized loss note (line 106)."""
        notes = generate_improvement_notes(
            account_return_pct=0.0,
            benchmark_return_pct=None,
            alpha=None,
            position_analysis=self._positions(),
            realized_pnl=-500.0,
        )
        assert any("realized losses" in n.lower() or "loss" in n.lower() for n in notes)

    def test_realized_gain_note(self) -> None:
        """realized_pnl > 0 → realized gain note (line 111)."""
        notes = generate_improvement_notes(
            account_return_pct=0.0,
            benchmark_return_pct=None,
            alpha=None,
            position_analysis=self._positions(),
            realized_pnl=250.0,
        )
        assert any("realized gains" in n.lower() or "gain" in n.lower() for n in notes)

    def test_empty_positions_no_worst_performer_note(self) -> None:
        notes = generate_improvement_notes(
            account_return_pct=0.0,
            benchmark_return_pct=None,
            alpha=None,
            position_analysis=[],
            realized_pnl=0.0,
        )
        assert isinstance(notes, list)
