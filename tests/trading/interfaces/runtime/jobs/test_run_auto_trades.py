from types import SimpleNamespace
import sys

import pytest

from trading.interfaces.runtime.jobs import run_auto_trades


def test_parse_args_reads_cli_values(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "auto_trader.py",
            "--accounts",
            "acct1,acct2",
            "--tickers-file",
            str(run_auto_trades.DEFAULT_TICKERS_FILE),
            "--min-trades",
            "2",
            "--max-trades",
            "7",
            "--fee",
            "1.25",
            "--seed",
            "99",
        ],
    )

    args = run_auto_trades.parse_args()
    assert args.accounts == "acct1,acct2"
    assert args.tickers_file == run_auto_trades.DEFAULT_TICKERS_FILE
    assert args.min_trades == 2
    assert args.max_trades == 7
    assert args.fee == pytest.approx(1.25)
    assert args.seed == 99


def test_main_validation_errors(monkeypatch) -> None:
    args = SimpleNamespace(
        min_trades=0,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/config/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: args)
    with pytest.raises(ValueError, match="min-trades"):
        run_auto_trades.main()


def test_main_happy_path_dispatches_accounts(monkeypatch, capsys) -> None:
    class _Conn:
        closed = False

        def close(self):
            self.closed = True

    conn = _Conn()
    args = SimpleNamespace(
        min_trades=1,
        max_trades=2,
        seed=123,
        accounts="acct1,acct2",
        tickers_file="trading/config/trade_universe.txt",
        fee=1.0,
    )

    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: args)
    monkeypatch.setattr(run_auto_trades, "load_tickers_from_file", lambda _p: ["AAPL", "MSFT"])
    monkeypatch.setattr(run_auto_trades, "fetch_latest_prices", lambda _u: {"AAPL": 100.0, "MSFT": 200.0})
    monkeypatch.setattr(run_auto_trades, "build_iv_rank_proxy", lambda _u: {"AAPL": 40.0})
    monkeypatch.setattr(run_auto_trades, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        run_auto_trades,
        "run_accounts_impl",
        lambda *_args, **_kwargs: [("acct1", 2), ("acct2", 2)],
    )

    run_auto_trades.main()

    out = capsys.readouterr().out
    assert "acct1: executed 2 trades" in out
    assert "acct2: executed 2 trades" in out
    assert conn.closed is True


def test_main_additional_validation_paths(monkeypatch) -> None:
    args = SimpleNamespace(
        min_trades=2,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/config/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: args)
    with pytest.raises(ValueError, match="max-trades"):
        run_auto_trades.main()

    args.max_trades = 2
    args.accounts = "  ,   "
    with pytest.raises(ValueError, match="No accounts"):
        run_auto_trades.main()


def test_main_empty_universe_and_no_prices(monkeypatch) -> None:
    args = SimpleNamespace(
        min_trades=1,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/config/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: args)

    monkeypatch.setattr(run_auto_trades, "load_tickers_from_file", lambda _p: [])
    with pytest.raises(ValueError, match="Ticker universe is empty"):
        run_auto_trades.main()

    monkeypatch.setattr(run_auto_trades, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(run_auto_trades, "fetch_latest_prices", lambda _u: {})
    with pytest.raises(ValueError, match="Could not fetch any prices"):
        run_auto_trades.main()


def test_main_closes_connection_when_run_accounts_fails(monkeypatch) -> None:
    class _Conn:
        closed = False

        def close(self):
            self.closed = True

    conn = _Conn()
    args = SimpleNamespace(
        min_trades=1,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/config/trade_universe.txt",
        fee=0.0,
    )

    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: args)
    monkeypatch.setattr(run_auto_trades, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(run_auto_trades, "fetch_latest_prices", lambda _u: {"AAPL": 100.0})
    monkeypatch.setattr(run_auto_trades, "build_iv_rank_proxy", lambda _u: {})
    monkeypatch.setattr(run_auto_trades, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        run_auto_trades,
        "run_accounts_impl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_auto_trades.main()

    assert conn.closed is True
