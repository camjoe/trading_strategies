from __future__ import annotations

import types
from pathlib import Path

import pytest

from trading.interfaces.cli.handlers.accounts_handlers import (
    handle_apply_account_preset,
    handle_apply_account_profiles,
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
        profit_take_pct=None,
        max_loss_pct=None,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def test_handle_init_prints_db_path(capsys) -> None:
    handle_init(None, types.SimpleNamespace(), _parser(), deps={}, module_file="", db_path="/data/paper.db")
    assert "/data/paper.db" in capsys.readouterr().out


def test_handle_create_account_calls_create_account_dep() -> None:
    calls: list = []
    deps = {"create_account": lambda *a, **kw: calls.append((a, kw))}
    args = _config_args(name="alice", strategy="trend", initial_cash=10000.0, benchmark="spy")

    handle_create_account(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert len(calls) == 1
    positional, _ = calls[0]
    assert positional[1] == "alice"
    assert positional[2] == "trend"
    assert positional[3] == 10000.0


def test_handle_create_account_routes_invalid_strategy_to_parser_error() -> None:
    deps = {"create_account": lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery'"))}
    args = _config_args(name="alice", strategy="mystery", initial_cash=10000.0, benchmark="spy")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery'"):
        handle_create_account(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_configure_account_calls_configure_account_dep() -> None:
    calls: list = []
    deps = {"configure_account": lambda *a, **kw: calls.append(kw)}
    args = _config_args(account="bob")

    handle_configure_account(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert calls[0]["account_name"] == "bob"


def test_handle_configure_account_routes_value_error_to_parser_error() -> None:
    # Both flags set triggers ValueError from resolve_learning_enabled
    args = _config_args(account="bob", learning_enabled=True, learning_disabled=True)

    with pytest.raises(SystemExit):
        handle_configure_account(object(), args, _parser(), deps={}, module_file="", db_path="")


def test_handle_apply_account_profiles_delegates_load_and_apply() -> None:
    loaded: list = []
    deps = {
        "load_account_profiles": lambda f: loaded.append(f) or [],
        "apply_account_profiles": lambda _conn, _profiles, create_missing: (1, 0, 0),
    }
    args = types.SimpleNamespace(file="profiles.yaml", no_create_missing=False)

    handle_apply_account_profiles(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert loaded == ["profiles.yaml"]


def test_handle_apply_account_profiles_routes_validation_error_to_parser_error() -> None:
    deps = {
        "load_account_profiles": lambda _f: [{"name": "acct"}],
        "apply_account_profiles": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = types.SimpleNamespace(file="profiles.yaml", no_create_missing=False)

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_apply_account_profiles(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_apply_account_preset_resolves_preset_path_and_loads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preset_path = tmp_path / "starter.yaml"
    preset_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "trading.interfaces.cli.handlers.accounts_handlers.get_builtin_profile_preset_path",
        lambda _preset: preset_path,
    )

    loaded: list = []
    deps = {
        "load_account_profiles": lambda f: loaded.append(f) or [],
        "apply_account_profiles": lambda *_a, **_kw: (0, 1, 0),
    }
    args = types.SimpleNamespace(preset="starter", no_create_missing=True)

    handle_apply_account_preset(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert loaded == [str(preset_path)]


def test_handle_apply_account_preset_routes_validation_error_to_parser_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preset_path = tmp_path / "starter.yaml"
    preset_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "trading.interfaces.cli.handlers.accounts_handlers.get_builtin_profile_preset_path",
        lambda _preset: preset_path,
    )

    deps = {
        "load_account_profiles": lambda _f: [{"name": "acct"}],
        "apply_account_profiles": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = types.SimpleNamespace(preset="starter", no_create_missing=True)

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_apply_account_preset(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_set_benchmark_calls_dep_with_correct_args() -> None:
    calls: list = []
    deps = {"set_benchmark": lambda _conn, account, benchmark: calls.append((account, benchmark))}
    args = types.SimpleNamespace(account="alice", benchmark="qqq")

    handle_set_benchmark(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert calls == [("alice", "qqq")]


def test_handle_list_accounts_calls_dep_with_conn() -> None:
    calls: list = []
    conn = object()
    deps = {"list_accounts": lambda c: calls.append(c)}

    handle_list_accounts(conn, types.SimpleNamespace(), _parser(), deps=deps, module_file="", db_path="")

    assert calls == [conn]


def test_handle_trade_delegates_all_fields_to_record_trade_dep() -> None:
    calls: list = []
    deps = {"record_trade": lambda *_a, **kw: calls.append(kw)}
    args = types.SimpleNamespace(
        account="alice", side="buy", ticker="AAPL", qty=10, price=150.0, fee=1.0, time=None, note="test"
    )

    handle_trade(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert calls[0]["account_name"] == "alice"
    assert calls[0]["ticker"] == "AAPL"
    assert calls[0]["side"] == "buy"
