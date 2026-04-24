import pytest

from trading.services.accounts import (
    build_account_listing_lines,
    format_account_policy_text,
    format_goal_text,
)
from tests.support import make_accounts_service_row


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
        row = make_accounts_service_row(
            goal_min_return_pct=goal_min,
            goal_max_return_pct=goal_max,
            goal_period=goal_period,
        )
        assert format_goal_text(row) == expected


class TestBuildAccountListingLines:
    def test_by_strategy_groups_and_inserts_headers(self) -> None:
        rows = [
            make_accounts_service_row(name="a1", strategy="Momentum"),
            make_accounts_service_row(name="a2", strategy="Momentum"),
            make_accounts_service_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=True)
        assert any("Base Strategy: Momentum" in line for line in lines)
        assert any("Base Strategy: Trend" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_flat_mode_omits_strategy_headers(self) -> None:
        rows = [
            make_accounts_service_row(name="a1", strategy="Momentum"),
            make_accounts_service_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=False)
        assert not any("Base Strategy:" in line for line in lines)
        assert any("a1" in line for line in lines)
        assert any("b1" in line for line in lines)

    def test_empty_list_returns_empty(self) -> None:
        assert build_account_listing_lines([], by_strategy=True) == []

    def test_strategy_change_inserts_blank_separator(self) -> None:
        rows = [
            make_accounts_service_row(name="a1", strategy="Momentum"),
            make_accounts_service_row(name="b1", strategy="Trend"),
        ]
        lines = build_account_listing_lines(rows, by_strategy=True)
        assert "" in lines

    def test_rotation_accounts_show_base_and_active_strategy(self) -> None:
        rows = [
            make_accounts_service_row(
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
    row = make_accounts_service_row(strategy="Trend")

    assert format_account_policy_text(row) == (
        "base_strategy=Trend | active_strategy=Trend | benchmark=SPY | "
        "heuristic_exploration=off | risk=none | instrument=equity | "
        "trade_size=10.00% | max_position=20.00%"
    )
