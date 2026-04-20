from __future__ import annotations

from trading.interfaces.cli.commands import build_parser


def test_trade_command_parses_optionals() -> None:
    parser = build_parser()

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


def test_compare_strategies_and_snapshot_history_defaults() -> None:
    parser = build_parser()

    compare_args = parser.parse_args(["compare-strategies"])
    history_args = parser.parse_args(["snapshot-history", "--account", "acct1"])
    promotion_args = parser.parse_args(["promotion-status", "--account", "acct1"])
    request_args = parser.parse_args(["promotion-request-review", "--account", "acct1"])
    review_history_args = parser.parse_args(["promotion-review-history", "--account", "acct1"])
    review_action_args = parser.parse_args(
        ["promotion-review-action", "--review-id", "7", "--action", "note"]
    )

    assert compare_args.lookback == 10
    assert history_args.limit == 20
    assert promotion_args.strategy is None
    assert request_args.requested_by is None
    assert review_history_args.limit == 10
    assert review_action_args.actor is None
