import pytest

from trading.models import AccountConfig
from trading.services.accounts import create_account, get_account, list_accounts, set_benchmark


class TestAccountListingOutput:
    def test_set_benchmark_updates_and_normalizes_ticker(self, conn) -> None:
        create_account(conn, "acct_bench", "Trend", 1000.0, "spy")

        set_benchmark(conn, "acct_bench", " qqq ")

        account = get_account(conn, "acct_bench")
        assert account["benchmark_ticker"] == "QQQ"

    def test_list_accounts_prints_empty_message_when_no_accounts(
        self,
        conn,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        list_accounts(conn)

        out = capsys.readouterr().out
        assert "No paper accounts found." in out

    @pytest.mark.parametrize(
        ("name", "goal_min", "goal_max", "goal_period", "expected_goal_text"),
        [
            ("acct_goal_none", None, None, "monthly", None),
            ("acct_goal_range", 1.5, 3.0, "weekly", "goal_metadata=1.50% to 3.00% per weekly"),
            ("acct_goal_min", 2.0, None, "monthly", "goal_metadata=>= 2.00% per monthly"),
            ("acct_goal_max", None, 4.5, "quarterly", "goal_metadata=<= 4.50% per quarterly"),
        ],
    )
    def test_list_accounts_formats_goal_variants(
        self,
        conn,
        capsys: pytest.CaptureFixture[str],
        name: str,
        goal_min: float | None,
        goal_max: float | None,
        goal_period: str,
        expected_goal_text: str | None,
    ) -> None:
        create_account(
            conn,
            name=name,
            strategy="Trend",
            initial_cash=5000.0,
            benchmark_ticker="spy",
            config=AccountConfig(
                goal_min_return_pct=goal_min,
                goal_max_return_pct=goal_max,
                goal_period=goal_period,
            ),
        )

        list_accounts(conn)

        out = capsys.readouterr().out
        if expected_goal_text is None:
            assert "goal_metadata=" not in out
        else:
            assert expected_goal_text in out
        assert "benchmark=SPY" in out

    def test_list_accounts_without_strategy_grouping(self, conn, capsys: pytest.CaptureFixture[str]) -> None:
        create_account(conn, "acct_a", "Trend", 1000.0, "SPY")
        create_account(conn, "acct_b", "MeanRev", 1000.0, "SPY")

        list_accounts(conn, by_strategy=False)

        out = capsys.readouterr().out
        assert "Strategy:" not in out
        assert "acct_a" in out
        assert "acct_b" in out
