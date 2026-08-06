from __future__ import annotations

import types

import pytest

from trading.interfaces.cli.handlers.router import COMMAND_HANDLERS, dispatch_command

_EXPECTED_COMMANDS = {
    "init",
    "create-account",
    "configure-account",
    "set-benchmark",
    "list-accounts",
    "trade",
    "report",
    "promotion-status",
    "promotion-request-review",
    "promotion-review-history",
    "promotion-review-action",
    "snapshot",
    "snapshot-history",
    "compare-strategies",
    "portfolio-exposure",
    "portfolio-concentration",
    "parameters",
    "configure-throttle",
    "configure-evaluation",
    "configure-promotion",
    "configure-book-rotation",
    "configure-book-rotation-policy",
    "settings-history",
    "book-rotation-history",
    "create-strategy-variant",
    "configure-strategy",
    "freeze-strategy",
    "backtest",
    "backtest-report",
    "backtest-leaderboard",
    "backtest-batch",
    "backtest-optimize",
    "backtest-optimize-show",
    "backtest-optimize-promote",
}


def test_command_handlers_registry_has_all_expected_commands() -> None:
    assert _EXPECTED_COMMANDS == set(COMMAND_HANDLERS.keys())


def test_dispatch_command_routes_to_registered_handler() -> None:
    calls: list = []
    original = COMMAND_HANDLERS["list-accounts"]
    COMMAND_HANDLERS["list-accounts"] = lambda *_a, **_kw: calls.append("dispatched")
    try:
        dispatch_command(
            None,
            types.SimpleNamespace(command="list-accounts"),
            None,
            deps={},
        )
    finally:
        COMMAND_HANDLERS["list-accounts"] = original

    assert calls == ["dispatched"]


def test_dispatch_command_calls_parser_error_for_unknown_command() -> None:
    class _StubParser:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    with pytest.raises(SystemExit):
        dispatch_command(
            None,
            types.SimpleNamespace(command="not-a-command"),
            _StubParser(),
            deps={},
        )


class _RecordingParser:
    def __init__(self) -> None:
        self.message: str | None = None

    def error(self, msg: str) -> None:
        self.message = msg


def test_dispatch_command_records_parser_error_then_returns() -> None:
    parser = _RecordingParser()

    result = dispatch_command(
        None,
        types.SimpleNamespace(command="not-a-command"),
        parser,
        deps={},
    )

    assert result is None
    assert parser.message == "Unsupported command: not-a-command"
