import sqlite3

import pytest

from trading.services.accounts_service import (
    build_account_listing_lines,
    format_goal_text,
)


def _goal_row(
    *,
    goal_min: float | None = None,
    goal_max: float | None = None,
    goal_period: str = "monthly",
) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE t (goal_min_return_pct REAL, goal_max_return_pct REAL, goal_period TEXT)"
    )
    conn.execute("INSERT INTO t VALUES (?, ?, ?)", [goal_min, goal_max, goal_period])
    return conn.execute("SELECT * FROM t").fetchone()


def _account_row(
    *,
    id: int = 1,
    name: str = "acct",
    descriptive_name: str = "Account",
    strategy: str = "Trend",
    initial_cash: float = 5000.0,
    benchmark_ticker: str = "SPY",
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str = "monthly",
    learning_enabled: int = 0,
    risk_policy: str = "none",
    instrument_mode: str = "equity",
    created_at: str = "2026-01-01T00:00:00",
) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE t (
            id INTEGER, name TEXT, descriptive_name TEXT, strategy TEXT,
            initial_cash REAL, benchmark_ticker TEXT,
            goal_min_return_pct REAL, goal_max_return_pct REAL, goal_period TEXT,
            learning_enabled INTEGER, risk_policy TEXT, instrument_mode TEXT, created_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            id, name, descriptive_name, strategy, initial_cash, benchmark_ticker,
            goal_min_return_pct, goal_max_return_pct, goal_period,
            learning_enabled, risk_policy, instrument_mode, created_at,
        ],
    )
    return conn.execute("SELECT * FROM t").fetchone()


class TestFormatGoalText:
    @pytest.mark.parametrize(
        ("goal_min", "goal_max", "goal_period", "expected"),
        [
            (None, None, "monthly", "not-set"),
            (1.5, 3.0, "weekly", "1.50% to 3.00% per weekly"),
            (2.0, None, "monthly", ">= 2.00% per monthly"),
            (None, 4.5, "quarterly", "<= 4.50% per quarterly"),
        ],
    )
    def test_variants(
        self,
        goal_min: float | None,
        goal_max: float | None,
        goal_period: str,
        expected: str,
    ) -> None:
        row = _goal_row(goal_min=goal_min, goal_max=goal_max, goal_period=goal_period)
        assert format_goal_text(row) == expected


class TestBuildAccountListingLines:
    def test_by_strategy_groups_and_inserts_headers(self) -> None:
        rows = [
            _account_row(name="a1", strategy="Momentum"),
            _account_row(name="a2", strategy="Momentum"),
            _account_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=True)
        assert any("Strategy: Momentum" in line for line in lines)
        assert any("Strategy: Trend" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_flat_mode_omits_strategy_headers(self) -> None:
        rows = [
            _account_row(name="a1", strategy="Momentum"),
            _account_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=False)
        assert not any("Strategy:" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_empty_list_returns_empty(self) -> None:
        assert build_account_listing_lines([], by_strategy=True) == []

    def test_strategy_change_inserts_blank_separator(self) -> None:
        rows = [
            _account_row(name="a1", strategy="Momentum"),
            _account_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=True)
        # A blank line separates strategy groups
        assert "" in lines
