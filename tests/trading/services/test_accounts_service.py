import sqlite3

import pytest

import trading.services.accounts_service as accounts_service
from trading.models.account_config import AccountConfig
from trading.services.accounts_service import (
    build_account_listing_lines,
    create_account,
    format_account_policy_text,
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
    trade_size_pct: float = 10.0,
    max_position_pct: float = 20.0,
    instrument_mode: str = "equity",
    created_at: str = "2026-01-01T00:00:00",
    rotation_enabled: int = 0,
    rotation_active_strategy: str | None = None,
) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE t (
            id INTEGER, name TEXT, descriptive_name TEXT, strategy TEXT,
            initial_cash REAL, benchmark_ticker TEXT,
            goal_min_return_pct REAL, goal_max_return_pct REAL, goal_period TEXT,
            learning_enabled INTEGER, risk_policy TEXT, trade_size_pct REAL, max_position_pct REAL,
            instrument_mode TEXT, created_at TEXT,
            rotation_enabled INTEGER, rotation_active_strategy TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            id, name, descriptive_name, strategy, initial_cash, benchmark_ticker,
            goal_min_return_pct, goal_max_return_pct, goal_period,
            learning_enabled, risk_policy, trade_size_pct, max_position_pct, instrument_mode, created_at,
            rotation_enabled, rotation_active_strategy,
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
        assert any("Base Strategy: Momentum" in line for line in lines)
        assert any("Base Strategy: Trend" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_flat_mode_omits_strategy_headers(self) -> None:
        rows = [
            _account_row(name="a1", strategy="Momentum"),
            _account_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=False)
        assert not any("Base Strategy:" in line for line in lines)
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

    def test_rotation_accounts_show_base_and_active_strategy(self) -> None:
        rows = [
            _account_row(
                name="rot",
                strategy="Trend",
                rotation_enabled=1,
                rotation_active_strategy="mean_reversion",
            ),
        ]

        lines = build_account_listing_lines(rows, by_strategy=False)

        assert "account_policy=base_strategy=Trend | active_strategy=mean_reversion" in lines[0]
        assert "display_name=Account" in lines[0]
        assert "heuristic_exploration=off" in lines[0]
        assert "goal_metadata=" not in lines[0]


def test_format_account_policy_text_for_non_rotation_account() -> None:
    row = _account_row(strategy="Trend")

    assert format_account_policy_text(row) == (
        "base_strategy=Trend | active_strategy=Trend | benchmark=SPY | "
        "heuristic_exploration=off | risk=none | instrument=equity | "
        "trade_size=10.00% | max_position=20.00%"
    )


def test_create_account_rejects_unknown_strategy_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from trading.services.accounts import mutations as account_mutations

    insert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        account_mutations,
        "insert_account",
        lambda *args, **kwargs: insert_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
        create_account(
            sqlite3.connect(":memory:"),
            "acct",
            "mystery_strategy",
            5000.0,
            "SPY",
            config=AccountConfig(),
        )

    assert insert_calls == []
