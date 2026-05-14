"""Tests for trading.services.analysis.fetch_account_analysis."""
from __future__ import annotations

import sqlite3

import pytest

from trading.services.analysis import fetch_account_analysis
from tests.support.analysis import (
    make_analysis_account,
    patch_analysis_market_data,
    record_analysis_buy,
)


# ---------------------------------------------------------------------------
# Return % and alpha
# ---------------------------------------------------------------------------

class TestReturnPct:
    def test_positive_return(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        # Buy AAPL at 100; price rises to 110 → equity = cash(900) + mv(1100) = 2000...
        # Actually initial_cash=1000 means cash starts at 1000; buying 1 share at 100 leaves 900 cash
        # market_value at 110 = 110, equity = 1010 → return = 1%
        record_analysis_buy(conn, account_id=row["id"], ticker="AAPL", qty=1.0, price=100.0)
        patch_analysis_market_data(monkeypatch, prices={"AAPL": 110.0})
        result = fetch_account_analysis(conn, row)
        assert result["accountReturnPct"] == pytest.approx(1.0)

    def test_negative_return(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        record_analysis_buy(conn, account_id=row["id"], ticker="AAPL", qty=1.0, price=100.0)
        patch_analysis_market_data(monkeypatch, prices={"AAPL": 90.0})
        result = fetch_account_analysis(conn, row)
        assert result["accountReturnPct"] == pytest.approx(-1.0)

    def test_no_trades_flat_return(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        patch_analysis_market_data(monkeypatch)
        result = fetch_account_analysis(conn, row)
        assert result["accountReturnPct"] == pytest.approx(0.0)


class TestAlpha:
    def test_alpha_computed_when_benchmark_available(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        record_analysis_buy(conn, account_id=row["id"], ticker="AAPL", qty=1.0, price=100.0)
        # strategy return = 1% (price 100→110), benchmark = 5%
        patch_analysis_market_data(monkeypatch, prices={"AAPL": 110.0}, benchmark=(1050.0, 5.0))
        result = fetch_account_analysis(conn, row)
        assert result["alphaPct"] == pytest.approx(1.0 - 5.0)

    def test_alpha_none_when_benchmark_unavailable(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        patch_analysis_market_data(monkeypatch)
        result = fetch_account_analysis(conn, row)
        assert result["alphaPct"] is None


# ---------------------------------------------------------------------------
# Deposit-model (initial_cash=0) — effective_initial fallback
# ---------------------------------------------------------------------------

class TestDepositModel:
    def test_uses_total_deposited_when_initial_cash_zero(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=0.0)
        # Deposit 1000 via CASH buy trade, then buy AAPL
        record_analysis_buy(conn, account_id=row["id"], ticker="CASH", qty=10.0, price=100.0)  # deposits 1000
        record_analysis_buy(conn, account_id=row["id"], ticker="AAPL", qty=1.0, price=100.0)   # spends 100
        # cash = 0 + 1000(deposit) - 100(buy) = 900; mv at 110 = 110; equity = 1010
        # effective_initial = total_deposited = 1000; return = 1%
        patch_analysis_market_data(monkeypatch, prices={"AAPL": 110.0})
        result = fetch_account_analysis(conn, row)
        assert result["accountReturnPct"] == pytest.approx(1.0)

    def test_zero_initial_and_zero_deposited_returns_zero(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=0.0)
        patch_analysis_market_data(monkeypatch)
        result = fetch_account_analysis(conn, row)
        assert result["accountReturnPct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# topWinners / topLosers — non-overlap regression
# ---------------------------------------------------------------------------

class TestTopWinnersLosers:
    def _make_prices_and_buys(
        self, conn: sqlite3.Connection, account_id: int, tickers_and_prices: list[tuple[str, float, float]]
    ) -> dict[str, float]:
        """Buy each ticker at buy_price; return prices dict at current_price."""
        prices: dict[str, float] = {}
        for ticker, buy_price, current_price in tickers_and_prices:
            record_analysis_buy(conn, account_id=account_id, ticker=ticker, qty=1.0, price=buy_price)
            prices[ticker] = current_price
        return prices

    def test_no_overlap_with_seven_positions(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: with 7 positions, no ticker should appear in both lists."""
        row = make_analysis_account(conn, "acct", initial_cash=10000.0)
        # 7 positions with varied returns (best→worst: +30, +20, +10, 0, -10, -20, -30)
        positions = [
            ("A", 100.0, 130.0),
            ("B", 100.0, 120.0),
            ("C", 100.0, 110.0),
            ("D", 100.0, 100.0),
            ("E", 100.0, 90.0),
            ("F", 100.0, 80.0),
            ("G", 100.0, 70.0),
        ]
        prices = self._make_prices_and_buys(conn, row["id"], positions)
        patch_analysis_market_data(monkeypatch, prices=prices)
        result = fetch_account_analysis(conn, row)
        winner_tickers = {p["ticker"] for p in result["topWinners"]}
        loser_tickers = {p["ticker"] for p in result["topLosers"]}
        assert winner_tickers.isdisjoint(loser_tickers), (
            f"Overlap between winners and losers: {winner_tickers & loser_tickers}"
        )

    def test_winners_sorted_best_first(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=10000.0)
        positions = [("A", 100.0, 130.0), ("B", 100.0, 120.0), ("C", 100.0, 110.0)]
        prices = self._make_prices_and_buys(conn, row["id"], positions)
        patch_analysis_market_data(monkeypatch, prices=prices)
        result = fetch_account_analysis(conn, row)
        pnl_pcts = [float(p["unrealizedPnlPct"]) for p in result["topWinners"]]
        assert pnl_pcts == sorted(pnl_pcts, reverse=True)

    def test_losers_sorted_worst_first(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=10000.0)
        positions = [("A", 100.0, 130.0), ("B", 100.0, 90.0), ("C", 100.0, 80.0), ("D", 100.0, 70.0)]
        prices = self._make_prices_and_buys(conn, row["id"], positions)
        patch_analysis_market_data(monkeypatch, prices=prices)
        result = fetch_account_analysis(conn, row)
        pnl_pcts = [float(p["unrealizedPnlPct"]) for p in result["topLosers"]]
        assert pnl_pcts == sorted(pnl_pcts)

    def test_fewer_than_five_positions_no_overlap(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge case: ≤5 positions — ensure no position is in both lists."""
        row = make_analysis_account(conn, "acct", initial_cash=5000.0)
        positions = [("A", 100.0, 130.0), ("B", 100.0, 80.0), ("C", 100.0, 95.0)]
        prices = self._make_prices_and_buys(conn, row["id"], positions)
        patch_analysis_market_data(monkeypatch, prices=prices)
        result = fetch_account_analysis(conn, row)
        winner_tickers = {p["ticker"] for p in result["topWinners"]}
        loser_tickers = {p["ticker"] for p in result["topLosers"]}
        assert winner_tickers.isdisjoint(loser_tickers)


# ---------------------------------------------------------------------------
# Return dict shape
# ---------------------------------------------------------------------------

class TestReturnShape:
    def test_required_keys_present(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        patch_analysis_market_data(monkeypatch)
        result = fetch_account_analysis(conn, row)
        for key in ("accountReturnPct", "benchmarkReturnPct", "alphaPct",
                    "realizedPnl", "unrealizedPnl", "equity",
                    "topWinners", "topLosers", "improvementNotes"):
            assert key in result, f"Missing key: {key}"

    def test_improvement_notes_is_list(self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        row = make_analysis_account(conn, "acct", initial_cash=1000.0)
        patch_analysis_market_data(monkeypatch)
        result = fetch_account_analysis(conn, row)
        assert isinstance(result["improvementNotes"], list)
