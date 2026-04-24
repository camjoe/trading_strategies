from __future__ import annotations

from unittest.mock import Mock

import pytest

from tests.support import make_run_auto_trades_args, run_auto_trades as module


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def install_main_args(monkeypatch, **overrides):
    monkeypatch.setattr(module, "parse_args", lambda: make_run_auto_trades_args(**overrides))


def test_main_validation_errors(monkeypatch) -> None:
    install_main_args(monkeypatch, min_trades=0, max_trades=1)

    with pytest.raises(ValueError, match="min-trades"):
        module.main()


def test_main_happy_path_dispatches_accounts(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_main_args(monkeypatch, min_trades=1, max_trades=2, seed=123, accounts="acct1,acct2", fee=1.0)
    monkeypatch.setattr(module, "load_tickers_from_file", lambda _p: ["AAPL", "MSFT"])
    monkeypatch.setattr(module, "fetch_latest_prices", lambda _u: {"AAPL": 100.0, "MSFT": 200.0})
    monkeypatch.setattr(module, "build_iv_rank_proxy", lambda _u: {"AAPL": 40.0})
    monkeypatch.setattr(module, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        module,
        "run_accounts_impl",
        lambda *_args, **_kwargs: [("acct1", 2), ("acct2", 2)],
    )

    module.main()

    out = capsys.readouterr().out
    assert "acct1: executed 2 trades" in out
    assert "acct2: executed 2 trades" in out
    assert conn.closed is True


def test_main_additional_validation_paths(monkeypatch) -> None:
    install_main_args(monkeypatch, min_trades=2, max_trades=1)

    with pytest.raises(ValueError, match="max-trades"):
        module.main()

    install_main_args(monkeypatch, min_trades=2, max_trades=2, accounts="  ,   ")

    with pytest.raises(ValueError, match="No accounts"):
        module.main()


def test_main_empty_universe_and_no_prices(monkeypatch) -> None:
    install_main_args(monkeypatch)
    monkeypatch.setattr(module, "load_tickers_from_file", lambda _p: [])

    with pytest.raises(ValueError, match="Ticker universe is empty"):
        module.main()

    monkeypatch.setattr(module, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(module, "fetch_latest_prices", lambda _u: {})

    with pytest.raises(ValueError, match="Could not fetch any prices"):
        module.main()


def test_main_closes_connection_when_run_accounts_fails(monkeypatch) -> None:
    conn = FakeConn()
    install_main_args(monkeypatch)
    monkeypatch.setattr(module, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(module, "fetch_latest_prices", lambda _u: {"AAPL": 100.0})
    monkeypatch.setattr(module, "build_iv_rank_proxy", lambda _u: {})
    monkeypatch.setattr(module, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        module,
        "run_accounts_impl",
        Mock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        module.main()

    assert conn.closed is True
