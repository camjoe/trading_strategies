import pytest

from trading.models import AccountConfig
from trading.services.accounts import configure_account, create_account, get_account, set_account_strategy

_IDENTITY_KEYS = frozenset({"name", "strategy", "initial_cash", "benchmark_ticker"})


class TestCreateAccountIntegration:
    @pytest.mark.parametrize(
        ("kwargs", "error_text"),
        [
            ({"initial_cash": 0}, "initial_cash must be greater than 0"),
            ({"risk_policy": "bad"}, "risk_policy must be one of"),
            ({"instrument_mode": "futures"}, "instrument_mode must be one of"),
            ({"goal_min_return_pct": 5, "goal_max_return_pct": 2}, "goal_min_return_pct cannot be greater"),
            ({"option_type": "strangle"}, "option_type must be one of"),
            ({"trade_size_pct": 0}, "trade_size_pct must be greater than 0 and <= 100"),
            ({"max_position_pct": 101}, "max_position_pct must be greater than 0 and <= 100"),
            ({"trade_size_pct": 25, "max_position_pct": 20}, "trade_size_pct cannot be greater than max_position_pct"),
        ],
    )
    def test_rejects_invalid_inputs(self, conn, kwargs: dict[str, object], error_text: str) -> None:
        all_kwargs: dict[str, object] = {
            "name": "acct_bad",
            "strategy": "Trend",
            "initial_cash": 1000.0,
            "benchmark_ticker": "SPY",
        }
        all_kwargs.update(kwargs)
        identity = {k: v for k, v in all_kwargs.items() if k in _IDENTITY_KEYS}
        config_kw = {k: v for k, v in all_kwargs.items() if k not in _IDENTITY_KEYS}

        with pytest.raises(ValueError, match=error_text):
            create_account(conn, **identity, config=AccountConfig(**config_kw))

    @pytest.mark.parametrize(
        ("kwargs", "error_text"),
        [
            ({"target_delta_max": 1.1}, "target_delta_max must be between 0 and 1"),
            ({"option_min_dte": -1}, "option_min_dte must be >= 0"),
            ({"option_max_dte": -1}, "option_max_dte must be >= 0"),
            ({"iv_rank_min": -0.1}, "iv_rank_min must be between 0 and 100"),
            ({"iv_rank_max": 101}, "iv_rank_max must be between 0 and 100"),
        ],
    )
    def test_rejects_invalid_option_setting_bounds(
        self,
        conn,
        kwargs: dict[str, object],
        error_text: str,
    ) -> None:
        all_kwargs: dict[str, object] = {
            "name": "acct_bad_bounds",
            "strategy": "Trend",
            "initial_cash": 1000.0,
            "benchmark_ticker": "SPY",
        }
        all_kwargs.update(kwargs)
        identity = {k: v for k, v in all_kwargs.items() if k in _IDENTITY_KEYS}
        config_kw = {k: v for k, v in all_kwargs.items() if k not in _IDENTITY_KEYS}

        with pytest.raises(ValueError, match=error_text):
            create_account(conn, **identity, config=AccountConfig(**config_kw))

    def test_normalizes_fields(self, conn) -> None:
        create_account(
            conn,
            name="acct_norm",
            strategy="Trend",
            initial_cash=2000.0,
            benchmark_ticker=" qqq ",
            config=AccountConfig(
                descriptive_name="  Growth Focus  ",
                goal_period=" Weekly ",
                option_type="call",
            ),
        )

        account = get_account(conn, "acct_norm")
        assert account["benchmark_ticker"] == "QQQ"
        assert account["descriptive_name"] == "Growth Focus"
        assert account["goal_period"] == "weekly"
        assert account["option_type"] == "call"

    def test_set_account_strategy_updates_validated_strategy(self, conn) -> None:
        create_account(conn, "acct_strategy", "Trend", 1000.0, "SPY")

        set_account_strategy(conn, "acct_strategy", "MeanRev")

        account = get_account(conn, "acct_strategy")
        assert account["strategy"] == "MeanRev"


class TestConfigureAccountIntegration:
    def test_no_fields_is_noop(self, conn, base_account) -> None:
        before = dict(get_account(conn, base_account))

        configure_account(conn, base_account)

        after = dict(get_account(conn, base_account))
        assert before == after

    def test_rejects_empty_descriptive_name(self, conn, base_account) -> None:
        with pytest.raises(ValueError, match="descriptive_name cannot be empty"):
            configure_account(conn, base_account, config=AccountConfig(descriptive_name="   "))

    def test_validates_goal_range_against_existing_values(self, conn) -> None:
        create_account(
            conn,
            "acct_goal_validate",
            "Trend",
            3000.0,
            "SPY",
            config=AccountConfig(goal_min_return_pct=5.0, goal_max_return_pct=10.0),
        )

        with pytest.raises(ValueError, match="goal_min_return_pct cannot be greater than goal_max_return_pct"):
            configure_account(conn, "acct_goal_validate", config=AccountConfig(goal_max_return_pct=4.0))

    def test_validates_existing_option_settings(self, conn) -> None:
        create_account(
            conn,
            "acct_opt_validate",
            "Trend",
            3000.0,
            "SPY",
            config=AccountConfig(
                option_type="call",
                target_delta_min=0.6,
                target_delta_max=0.9,
                iv_rank_min=10.0,
                iv_rank_max=80.0,
            ),
        )

        with pytest.raises(ValueError, match="target_delta_min cannot be greater than target_delta_max"):
            configure_account(conn, "acct_opt_validate", config=AccountConfig(target_delta_max=0.5))

    def test_validates_iv_range_against_existing_values(self, conn) -> None:
        create_account(
            conn,
            "acct_iv_validate",
            "Trend",
            3000.0,
            "SPY",
            config=AccountConfig(iv_rank_min=20.0, iv_rank_max=90.0),
        )

        with pytest.raises(ValueError, match="iv_rank_min cannot be greater than iv_rank_max"):
            configure_account(conn, "acct_iv_validate", config=AccountConfig(iv_rank_max=10.0))

    def test_normalizes_goal_period_and_learning_enabled(self, conn, base_account) -> None:
        configure_account(
            conn,
            base_account,
            config=AccountConfig(goal_period=" Weekly ", learning_enabled=True),
        )

        account = get_account(conn, base_account)
        assert account["goal_period"] == "weekly"
        assert int(account["learning_enabled"]) == 1

    def test_validates_position_sizing_against_existing_values(self, conn) -> None:
        create_account(
            conn,
            "acct_sizing_validate",
            "Trend",
            3000.0,
            "SPY",
            config=AccountConfig(trade_size_pct=8.0, max_position_pct=16.0),
        )

        with pytest.raises(ValueError, match="trade_size_pct cannot be greater than max_position_pct"):
            configure_account(conn, "acct_sizing_validate", config=AccountConfig(trade_size_pct=20.0))

    @pytest.mark.parametrize(
        ("kwargs", "error_text"),
        [
            ({"risk_policy": "bad_policy"}, "risk_policy must be one of"),
            ({"instrument_mode": "futures"}, "instrument_mode must be one of"),
            ({"option_type": "strangle"}, "option_type must be one of"),
        ],
    )
    def test_rejects_invalid_enum_inputs(
        self,
        conn,
        base_account,
        kwargs: dict[str, object],
        error_text: str,
    ) -> None:
        with pytest.raises(ValueError, match=error_text):
            configure_account(conn, base_account, config=AccountConfig(**kwargs))


class TestConfigureAccountOptionFields:
    def test_configure_account_updates_risk_and_option_fields(self, conn, base_account) -> None:
        configure_account(
            conn,
            account_name=base_account,
            config=AccountConfig(
                risk_policy="stop_and_target",
                stop_loss_pct=5.0,
                take_profit_pct=10.0,
                instrument_mode="leaps",
                option_strike_offset_pct=4.0,
                option_min_dte=150,
                option_max_dte=365,
            ),
        )

        account = get_account(conn, base_account)
        assert account["risk_policy"] == "stop_and_target"
        assert float(account["stop_loss_pct"]) == pytest.approx(5.0)
        assert float(account["take_profit_pct"]) == pytest.approx(10.0)
        assert account["instrument_mode"] == "leaps"
        assert float(account["option_strike_offset_pct"]) == pytest.approx(4.0)
        assert int(account["option_min_dte"]) == 150
        assert int(account["option_max_dte"]) == 365

    def test_configure_account_updates_position_sizing_fields(self, conn, base_account) -> None:
        configure_account(
            conn,
            account_name=base_account,
            config=AccountConfig(trade_size_pct=12.0, max_position_pct=24.0),
        )

        account = get_account(conn, base_account)
        assert float(account["trade_size_pct"]) == pytest.approx(12.0)
        assert float(account["max_position_pct"]) == pytest.approx(24.0)

    def test_create_account_rejects_invalid_option_dte_range(self, conn) -> None:
        with pytest.raises(ValueError, match="option_min_dte cannot be greater than option_max_dte"):
            create_account(
                conn,
                name="bad_dte",
                strategy="Trend",
                initial_cash=5000,
                benchmark_ticker="SPY",
                config=AccountConfig(
                    instrument_mode="leaps",
                    option_min_dte=365,
                    option_max_dte=120,
                ),
            )

    @pytest.mark.parametrize(
        ("kwargs", "error_text"),
        [
            ({"iv_rank_min": 80, "iv_rank_max": 20}, "iv_rank_min cannot be greater than iv_rank_max"),
            ({"target_delta_min": 1.2}, "target_delta_min must be between 0 and 1"),
        ],
    )
    def test_configure_account_rejects_invalid_range(
        self,
        conn,
        base_account,
        kwargs: dict[str, object],
        error_text: str,
    ) -> None:
        with pytest.raises(ValueError, match=error_text):
            configure_account(conn, account_name=base_account, config=AccountConfig(**kwargs))
