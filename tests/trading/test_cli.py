import pytest

from trading import cli


class TestBuildParserCore:
    def test_requires_command(self):
        parser = cli.build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_create_account_defaults_and_required_fields(self):
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "create-account",
                "--name",
                "acct1",
                "--strategy",
                "trend",
                "--initial-cash",
                "10000",
            ]
        )

        assert args.command == "create-account"
        assert args.benchmark == "SPY"
        assert args.goal_period == "monthly"
        assert args.learning_enabled is False
        assert args.risk_policy == "none"
        assert args.instrument_mode == "equity"
        assert args.option_type is None

    def test_configure_account_defaults_do_not_force_values(self):
        parser = cli.build_parser()

        args = parser.parse_args(["configure-account", "--account", "acct1"])

        assert args.command == "configure-account"
        assert args.goal_period is None
        assert args.risk_policy is None
        assert args.instrument_mode is None
        assert args.learning_enabled is False
        assert args.learning_disabled is False


class TestOptionAndEnumArguments:
    @pytest.mark.parametrize(
        "option_type",
        ["call", "put", "both"],
    )
    def test_option_type_choices_parse_for_create_account(self, option_type: str):
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "create-account",
                "--name",
                "acct1",
                "--strategy",
                "trend",
                "--initial-cash",
                "5000",
                "--option-type",
                option_type,
            ]
        )

        assert args.option_type == option_type

    @pytest.mark.parametrize(
        "instrument_mode,risk_policy",
        [
            ("equity", "none"),
            ("leaps", "fixed_stop"),
            ("equity", "take_profit"),
            ("leaps", "stop_and_target"),
        ],
    )
    def test_enum_choices_parse_for_configure_account(self, instrument_mode: str, risk_policy: str):
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "configure-account",
                "--account",
                "acct1",
                "--instrument-mode",
                instrument_mode,
                "--risk-policy",
                risk_policy,
            ]
        )

        assert args.instrument_mode == instrument_mode
        assert args.risk_policy == risk_policy

    def test_trade_command_parses_optionals(self):
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "trade",
                "--account",
                "acct1",
                "--side",
                "buy",
                "--ticker",
                "AAPL",
                "--qty",
                "2",
                "--price",
                "100.5",
                "--fee",
                "1.25",
                "--time",
                "2026-03-14T10:00:00",
                "--note",
                "sizing test",
            ]
        )

        assert args.fee == 1.25
        assert args.time == "2026-03-14T10:00:00"
        assert args.note == "sizing test"


class TestBacktestParserDefaults:
    def test_backtest_defaults(self):
        parser = cli.build_parser()

        args = parser.parse_args(["backtest", "--account", "acct1"])

        assert args.tickers_file == "trading/trade_universe.txt"
        assert args.slippage_bps == 5.0
        assert args.fee == 0.0
        assert args.allow_approximate_leaps is False

    def test_backtest_batch_parses_accounts_and_defaults(self):
        parser = cli.build_parser()

        args = parser.parse_args(["backtest-batch", "--accounts", "acct1,acct2"])

        assert args.accounts == "acct1,acct2"
        assert args.run_name_prefix is None
        assert args.allow_approximate_leaps is False

    def test_compare_strategies_and_snapshot_history_defaults(self):
        parser = cli.build_parser()

        compare_args = parser.parse_args(["compare-strategies"])
        history_args = parser.parse_args(["snapshot-history", "--account", "acct1"])

        assert compare_args.lookback == 10
        assert history_args.limit == 20


class TestProfileParserDefaults:
    def test_apply_account_profiles_defaults(self):
        parser = cli.build_parser()

        args = parser.parse_args(["apply-account-profiles"])

        assert args.file == "trading/account_profiles/default.json"
        assert args.no_create_missing is False

    def test_apply_account_preset_requires_choice(self):
        parser = cli.build_parser()

        args = parser.parse_args(["apply-account-preset", "--preset", "aggressive"])

        assert args.preset == "aggressive"
        assert args.no_create_missing is False
