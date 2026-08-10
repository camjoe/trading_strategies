from __future__ import annotations

import types

import pytest

import trading.interfaces.cli.handlers.accounts_handlers as module
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser, make_ctx, patch_services
from trading.interfaces.cli.handlers.accounts_handlers import (
    handle_configure_account,
    handle_create_account,
    handle_init,
    handle_list_accounts,
    handle_set_benchmark,
    handle_trade,
)


def _config_args(**kwargs) -> types.SimpleNamespace:
    """Minimal args satisfying common_account_config_kwargs."""
    defaults = dict(
        learning_enabled=False,
        learning_disabled=False,
        display_name=None,
        goal_min_return_pct=None,
        goal_max_return_pct=None,
        goal_period=None,
        risk_policy=None,
        stop_loss_pct=None,
        take_profit_pct=None,
        instrument_mode=None,
        option_strike_offset_pct=None,
        option_min_dte=None,
        option_max_dte=None,
        option_type=None,
        target_delta_min=None,
        target_delta_max=None,
        max_premium_per_trade=None,
        max_contracts_per_trade=None,
        iv_rank_min=None,
        iv_rank_max=None,
        roll_dte_threshold=None,
        option_profit_take_pct=None,
        option_max_loss_pct=None,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_handle_init_prints_db_path(capsys) -> None:
    ctx = make_ctx(db_path="/data/paper.db")
    handle_init(None, types.SimpleNamespace(), fake_parser(), ctx=ctx)
    # Rendered by the platform: a Path prints with the local separator.
    assert str(ctx.db_path) in capsys.readouterr().out


def test_handle_create_account_calls_create_account_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, create_account=lambda *a, **kw: calls.append((a, kw)))
    args = _config_args(name="alice", strategy="trend", initial_cash=10000.0, benchmark="spy")

    handle_create_account(object(), args, fake_parser(), ctx=make_ctx())

    assert len(calls) == 1
    positional, _ = calls[0]
    assert positional[1] == "alice"
    assert positional[2] == "trend"
    assert positional[3] == 10000.0


def test_handle_create_account_routes_invalid_strategy_to_parser_error(monkeypatch) -> None:
    patch_services(
        monkeypatch,
        module,
        create_account=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery'")),
    )
    args = _config_args(name="alice", strategy="mystery", initial_cash=10000.0, benchmark="spy")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery'"):
        handle_create_account(object(), args, fake_parser(), ctx=make_ctx())


def test_handle_configure_account_calls_configure_account_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, configure_account=lambda *a, **kw: calls.append(kw))
    args = _config_args(account="bob")

    handle_configure_account(object(), args, fake_parser(), ctx=make_ctx())

    assert calls[0]["account_name"] == "bob"


def test_handle_configure_account_routes_value_error_to_parser_error() -> None:
    # Both flags set triggers ValueError from resolve_learning_enabled
    args = _config_args(account="bob", learning_enabled=True, learning_disabled=True)

    with pytest.raises(SystemExit):
        handle_configure_account(object(), args, fake_parser(), ctx=make_ctx())


def test_handle_set_benchmark_calls_dep_with_correct_args(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch, module, set_benchmark=lambda _conn, account, benchmark: calls.append((account, benchmark))
    )
    args = types.SimpleNamespace(account="alice", benchmark="qqq")

    handle_set_benchmark(object(), args, fake_parser(), ctx=make_ctx())

    assert calls == [("alice", "qqq")]


def test_handle_list_accounts_prints_lines(capsys, monkeypatch) -> None:
    conn = object()
    patch_services(monkeypatch, module, list_accounts=lambda c: ["[1] acct1", "[2] acct2"])

    handle_list_accounts(conn, types.SimpleNamespace(), fake_parser(), ctx=make_ctx())

    out = capsys.readouterr().out
    assert "[1] acct1" in out
    assert "[2] acct2" in out


def test_handle_list_accounts_prints_empty_message(capsys, monkeypatch) -> None:
    conn = object()
    patch_services(monkeypatch, module, list_accounts=lambda c: [])

    handle_list_accounts(conn, types.SimpleNamespace(), fake_parser(), ctx=make_ctx())

    assert "No accounts found." in capsys.readouterr().out


def test_handle_trade_delegates_all_fields_to_record_trade_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, record_trade=lambda *_a, **kw: calls.append(kw))
    args = types.SimpleNamespace(
        account="alice", side="buy", ticker="AAPL", qty=10, price=150.0, fee=1.0, time=None, note="test"
    )

    handle_trade(object(), args, fake_parser(), ctx=make_ctx())

    assert calls[0]["account_name"] == "alice"
    assert calls[0]["ticker"] == "AAPL"
    assert calls[0]["side"] == "buy"


class _RecordingParser:
    def __init__(self) -> None:
        self.message: str | None = None

    def error(self, msg: str) -> None:
        self.message = msg


def test_handle_create_account_records_parser_error_without_printing_success(capsys, monkeypatch) -> None:
    parser = _RecordingParser()
    patch_services(
        monkeypatch, module, create_account=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad create"))
    )
    args = _config_args(name="alice", strategy="mystery", initial_cash=10000.0, benchmark="spy")

    handle_create_account(object(), args, parser, ctx=make_ctx())

    assert parser.message == "bad create"
    assert "Created account" not in capsys.readouterr().out


def test_handle_configure_account_records_parser_error_without_printing_success(capsys) -> None:
    parser = _RecordingParser()
    args = _config_args(account="bob", learning_enabled=True, learning_disabled=True)

    handle_configure_account(object(), args, parser, ctx=make_ctx())

    assert parser.message == "Use only one of --learning-enabled or --learning-disabled"
    assert "Updated account configuration" not in capsys.readouterr().out
