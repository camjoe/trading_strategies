import pytest

from tests.support.account_records import make_book_record
from tests.support.accounts import make_accounts_service_row
from trading.services.accounts.presentation import (
    render_account_listing_lines,
    render_account_policy_text,
    render_goal_text,
)


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
        # Goals are book columns (revision 0008).
        book = make_book_record(
            goal_min_return_pct=goal_min,
            goal_max_return_pct=goal_max,
            goal_period=goal_period,
        )
        assert render_goal_text(book) == expected

    def test_missing_book_is_not_set(self) -> None:
        assert render_goal_text(None) == "not-set"


class TestBuildAccountListingLines:
    def test_by_strategy_groups_and_inserts_headers(self) -> None:
        rows = [
            make_accounts_service_row(id=1, name="a1"),
            make_accounts_service_row(id=2, name="a2"),
            make_accounts_service_row(id=3, name="b1"),
        ]
        active = {1: "momentum", 2: "momentum", 3: "trend"}
        lines = render_account_listing_lines(rows, by_strategy=True, active_strategies=active)
        assert any("Strategy: momentum" in line for line in lines)
        assert any("Strategy: trend" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_flat_mode_omits_strategy_headers(self) -> None:
        rows = [
            make_accounts_service_row(id=1, name="a1"),
            make_accounts_service_row(id=2, name="b1"),
        ]
        lines = render_account_listing_lines(rows, by_strategy=False, active_strategies={1: "momentum", 2: "trend"})
        assert not any(line.startswith("Strategy:") for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_empty_list_returns_empty(self) -> None:
        assert render_account_listing_lines([], by_strategy=True) == []

    def test_strategy_change_inserts_blank_separator(self) -> None:
        rows = [
            make_accounts_service_row(id=1, name="a1"),
            make_accounts_service_row(id=2, name="b1"),
        ]
        lines = render_account_listing_lines(rows, by_strategy=True, active_strategies={1: "momentum", 2: "trend"})
        assert "" in lines

    def test_rotation_accounts_show_active_strategy(self) -> None:
        # The active strategy comes from the default-book assignment (ADR 014);
        # accounts.strategy was dropped in revision 0008.
        rows = [make_accounts_service_row(name="rot")]

        lines = render_account_listing_lines(rows, by_strategy=False, active_strategies={rows[0].id: "mean_reversion"})

        assert "account_policy=active_strategy=mean_reversion" in lines[0]
        assert "display_name=Account" in lines[0]
        assert "heuristic_exploration=off" in lines[0]
        assert "goal_metadata=" not in lines[0]


def test_render_account_policy_text_defaults() -> None:
    row = make_accounts_service_row()
    book = make_book_record(trade_size_pct=10.0, max_position_pct=20.0)

    assert render_account_policy_text(row, active_strategy="trend", book=book) == (
        "active_strategy=trend | benchmark=SPY | "
        "heuristic_exploration=off | risk=none | instrument=equity | "
        "trade_size=10.00% | max_position=20.00%"
    )
