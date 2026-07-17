from __future__ import annotations

import pytest

from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.commands.settings import float_or_none, int_or_none


def test_nullable_types_parse_none_and_values() -> None:
    assert int_or_none("none") is None
    assert int_or_none("15") == 15
    assert float_or_none("NONE") is None
    assert float_or_none("0.25") == 0.25


def test_configure_throttle_omitted_flags_are_absent() -> None:
    parser = build_parser()

    args = parser.parse_args(["configure-throttle", "--max-trades-per-day", "20"])

    assert args.max_trades_per_day == 20
    assert not hasattr(args, "max_trades_per_minute")


def test_configure_throttle_none_clears() -> None:
    parser = build_parser()

    args = parser.parse_args(["configure-throttle", "--max-trades-per-day", "none"])

    assert args.max_trades_per_day is None


def test_configure_evaluation_and_promotion_parse_typed_flags() -> None:
    parser = build_parser()

    evaluation_args = parser.parse_args(["configure-evaluation", "--backtest-evidence-weight", "0.7"])
    promotion_args = parser.parse_args(["configure-promotion", "--min-live-overall-confidence", "0.75"])

    assert evaluation_args.backtest_evidence_weight == 0.7
    assert not hasattr(evaluation_args, "paper_live_evidence_weight")
    assert promotion_args.min_live_overall_confidence == 0.75


def test_configure_book_rotation_policy_requires_account() -> None:
    parser = build_parser()

    args = parser.parse_args(["configure-book-rotation-policy", "--account", "acct1", "--cooldown-days", "10"])
    assert args.account == "acct1"
    assert args.book is None
    assert args.cooldown_days == 10
    assert not hasattr(args, "stability_weight")

    with pytest.raises(SystemExit):
        parser.parse_args(["configure-book-rotation-policy", "--cooldown-days", "10"])


def test_parameters_account_filter_defaults_to_none() -> None:
    parser = build_parser()

    args = parser.parse_args(["parameters"])

    assert args.account is None


def test_configure_book_rotation_parses_typed_flags() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "configure-book-rotation",
            "--account",
            "acct1",
            "--enabled",
            "true",
            "--schedule",
            "trend, meanrev",
            "--lookback-days",
            "45",
        ]
    )
    assert args.enabled is True
    assert args.schedule == ["trend", "meanrev"]
    assert args.lookback_days == 45

    cleared = parser.parse_args(
        ["configure-book-rotation", "--account", "acct1", "--schedule", "none", "--lookback-days", "none"]
    )
    assert cleared.schedule is None
    assert cleared.lookback_days is None


def test_configure_book_rotation_omitted_flags_are_absent() -> None:
    parser = build_parser()

    args = parser.parse_args(["configure-book-rotation", "--account", "acct1", "--enabled", "false"])

    assert args.enabled is False
    assert not hasattr(args, "schedule")
    assert not hasattr(args, "lookback_days")
