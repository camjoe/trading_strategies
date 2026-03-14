from types import SimpleNamespace

import pytest

from trading import paper_trading


class _FakeParser:
    def __init__(self, args):
        self._args = args

    def parse_args(self):
        return self._args

    def error(self, message: str):
        raise RuntimeError(message)


class _FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _configure_args(**overrides):
    base = {
        "command": "configure-account",
        "account": "acct1",
        "display_name": None,
        "goal_min_return_pct": None,
        "goal_max_return_pct": None,
        "goal_period": None,
        "learning_enabled": False,
        "learning_disabled": False,
        "risk_policy": None,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "instrument_mode": None,
        "option_strike_offset_pct": None,
        "option_min_dte": None,
        "option_max_dte": None,
        "option_type": None,
        "target_delta_min": None,
        "target_delta_max": None,
        "max_premium_per_trade": None,
        "max_contracts_per_trade": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "roll_dte_threshold": None,
        "profit_take_pct": None,
        "max_loss_pct": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_main_trade_dispatches_and_closes_connection(monkeypatch, capsys):
    fake_conn = _FakeConn()
    args = SimpleNamespace(
        command="trade",
        account="acct1",
        side="buy",
        ticker="AAPL",
        qty=2,
        price=100.5,
        fee=1.25,
        time="2026-03-14T10:00:00",
        note="test",
    )

    captured = {}

    def fake_record_trade(conn, **kwargs):
        captured["conn"] = conn
        captured["kwargs"] = kwargs

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "record_trade", fake_record_trade)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["kwargs"] == {
        "account_name": "acct1",
        "side": "buy",
        "ticker": "AAPL",
        "qty": 2,
        "price": 100.5,
        "fee": 1.25,
        "trade_time": "2026-03-14T10:00:00",
        "note": "test",
    }
    assert "Trade recorded." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_configure_account_conflicting_learning_flags_errors(monkeypatch):
    fake_conn = _FakeConn()
    args = _configure_args(learning_enabled=True, learning_disabled=True)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("configure_account should not be called")

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "configure_account", fail_if_called)

    with pytest.raises(RuntimeError, match="Use only one of --learning-enabled or --learning-disabled"):
        paper_trading.main()

    assert fake_conn.closed is True


def test_main_unknown_command_errors_and_closes_connection(monkeypatch):
    fake_conn = _FakeConn()
    args = SimpleNamespace(command="unknown")

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)

    with pytest.raises(RuntimeError, match="Unsupported command: unknown"):
        paper_trading.main()

    assert fake_conn.closed is True


def test_common_account_config_kwargs_create_sets_learning_enabled():
    args = _configure_args(command="create-account", learning_enabled=True)
    kwargs = paper_trading._common_account_config_kwargs(args, include_learning_disabled=False)
    assert kwargs["learning_enabled"] is True


def test_main_create_account_defaults_learning_disabled(monkeypatch):
    fake_conn = _FakeConn()
    args = _configure_args(
        command="create-account",
        name="acct1",
        strategy="Momentum",
        initial_cash=5000.0,
        benchmark="SPY",
        learning_enabled=False,
    )

    captured: dict[str, object] = {}

    def fake_create_account(conn, name, strategy, initial_cash, benchmark, **kwargs):
        captured["conn"] = conn
        captured["name"] = name
        captured["strategy"] = strategy
        captured["initial_cash"] = initial_cash
        captured["benchmark"] = benchmark
        captured["kwargs"] = kwargs

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "create_account", fake_create_account)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["name"] == "acct1"
    assert captured["strategy"] == "Momentum"
    assert captured["initial_cash"] == 5000.0
    assert captured["benchmark"] == "SPY"
    assert captured["kwargs"]["learning_enabled"] is False
    assert fake_conn.closed is True
