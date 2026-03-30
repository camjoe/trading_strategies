from __future__ import annotations

from trading.interfaces.cli.commands import build_parser
from trading.profile_source import DEFAULT_TICKERS_FILE


def test_backtest_defaults() -> None:
    parser = build_parser()

    args = parser.parse_args(["backtest", "--account", "acct1"])

    assert args.tickers_file == DEFAULT_TICKERS_FILE
    assert args.slippage_bps == 5.0
    assert args.fee == 0.0
    assert args.allow_approximate_leaps is False


def test_backtest_batch_parses_accounts_and_defaults() -> None:
    parser = build_parser()

    args = parser.parse_args(["backtest-batch", "--accounts", "acct1,acct2"])

    assert args.accounts == "acct1,acct2"
    assert args.run_name_prefix is None
    assert args.allow_approximate_leaps is False