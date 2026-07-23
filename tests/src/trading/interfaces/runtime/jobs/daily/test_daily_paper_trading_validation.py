from trading.interfaces.runtime.jobs.daily.paper_trading.arguments import build_parser
from trading.interfaces.runtime.jobs.daily.paper_trading.validation import (
    validate_account_trade_cap_overrides,
    validate_trade_count_args,
)


def _args(**overrides):
    defaults = {
        "primary_min_trades": 1,
        "primary_max_trades": 5,
        "other_min_trades": 1,
        "other_max_trades": 11,
        "shadow_eval_rolling_window_days": None,
    }
    defaults.update(overrides)
    return build_parser().parse_args(
        [
            "--primary-min-trades",
            str(defaults["primary_min_trades"]),
            "--primary-max-trades",
            str(defaults["primary_max_trades"]),
            "--other-min-trades",
            str(defaults["other_min_trades"]),
            "--other-max-trades",
            str(defaults["other_max_trades"]),
            *(
                ["--shadow-eval-rolling-window-days", str(defaults["shadow_eval_rolling_window_days"])]
                if defaults["shadow_eval_rolling_window_days"] is not None
                else []
            ),
        ]
    )


def test_validate_trade_count_args_accepts_valid_defaults() -> None:
    assert validate_trade_count_args(_args()) is None


def test_validate_trade_count_args_rejects_non_positive_primary_min() -> None:
    assert validate_trade_count_args(_args(primary_min_trades=0)) == "--primary-min-trades must be >= 1"


def test_validate_trade_count_args_rejects_primary_max_below_min() -> None:
    error = validate_trade_count_args(_args(primary_min_trades=5, primary_max_trades=4))
    assert error == "--primary-max-trades must be >= --primary-min-trades"


def test_validate_trade_count_args_rejects_non_positive_other_min() -> None:
    assert validate_trade_count_args(_args(other_min_trades=0)) == "--other-min-trades must be >= 1"


def test_validate_trade_count_args_rejects_other_max_below_min() -> None:
    error = validate_trade_count_args(_args(other_min_trades=6, other_max_trades=5))
    assert error == "--other-max-trades must be >= --other-min-trades"


def test_validate_trade_count_args_rejects_non_positive_shadow_window() -> None:
    error = validate_trade_count_args(_args(shadow_eval_rolling_window_days=0))
    assert error == "--shadow-eval-rolling-window-days must be >= 1"


def test_validate_account_trade_cap_overrides_passes_when_all_known() -> None:
    assert validate_account_trade_cap_overrides({"acct_a": (1, 5)}, ["acct_a", "acct_b"]) is None


def test_validate_account_trade_cap_overrides_reports_unknown() -> None:
    error = validate_account_trade_cap_overrides({"ghost": (1, 5)}, ["acct_a"])
    assert error == "Unknown account(s) in --account-trade-caps: ghost"


def test_build_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.accounts == "all"
    assert args.primary_max_trades == 5
    assert args.run_source == "scheduled-daily"
