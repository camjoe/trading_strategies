from types import SimpleNamespace

import pandas as pd
import pytest

from trading import auto_trader


def _base_account(**overrides):
    base = {
        "option_strike_offset_pct": 5.0,
        "target_delta_min": None,
        "target_delta_max": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "max_contracts_per_trade": None,
        "max_premium_per_trade": None,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
        "learning_enabled": 0,
        "risk_policy": "none",
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "instrument_mode": "equity",
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
        "rotation_enabled": 0,
        "rotation_interval_days": None,
        "rotation_schedule": None,
        "rotation_active_index": 0,
        "rotation_last_at": None,
        "rotation_active_strategy": None,
    }
    base.update(overrides)
    return base


def test_load_tickers_from_file_dedupes_ignores_comments(tmp_path):
    ticker_file = tmp_path / "tickers.txt"
    ticker_file.write_text("# comment\naapl, msft\nAAPL TSLA\n\nspy\n", encoding="utf-8")
    assert auto_trader.load_tickers_from_file(str(ticker_file)) == ["AAPL", "MSFT", "TSLA", "SPY"]


def test_load_tickers_from_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        auto_trader.load_tickers_from_file(str(tmp_path / "missing.txt"))


def test_choose_qty_helpers(monkeypatch):
    monkeypatch.setattr(auto_trader.random, "randint", lambda a, b: b)
    assert auto_trader.choose_buy_qty(cash=10.0, price=11.0, fee=0.0) == 0
    assert auto_trader.choose_buy_qty(cash=100.0, price=10.0, fee=0.0) == 5
    assert auto_trader.choose_sell_qty(position_qty=0.2) == 0
    assert auto_trader.choose_sell_qty(position_qty=9.0) == 5


def test_estimate_helpers_boundaries():
    assert auto_trader.estimate_delta(0.0) == pytest.approx(0.55)
    assert auto_trader.estimate_delta(1000.0) == pytest.approx(0.05)
    premium = auto_trader.estimate_option_premium(underlying_price=100.0, delta_est=0.4, min_dte=100, max_dte=200)
    assert premium > 0.5


def test_option_candidate_allowed_with_delta_and_iv_filters():
    account = _base_account(target_delta_min=0.6)
    ok, _, _ = auto_trader.option_candidate_allowed(account, "AAPL", 100.0, {"AAPL": 50.0})
    assert ok is False

    account = _base_account(iv_rank_min=20.0)
    ok, _, iv_rank = auto_trader.option_candidate_allowed(account, "AAPL", 100.0, {})
    assert ok is False
    assert iv_rank == -1.0

    account = _base_account(target_delta_min=0.1, target_delta_max=0.9, iv_rank_min=10.0, iv_rank_max=90.0)
    ok, delta, iv_rank = auto_trader.option_candidate_allowed(account, "AAPL", 100.0, {"AAPL": 50.0})
    assert ok is True
    assert 0.0 <= delta <= 1.0
    assert iv_rank == 50.0


def test_apply_leaps_buy_qty_limits():
    account = _base_account(max_contracts_per_trade=3, max_premium_per_trade=250.0)
    qty = auto_trader._apply_leaps_buy_qty_limits(qty=5, option_price=100.0, account=account)
    assert qty == 2


def test_build_trade_note_for_leaps_buy():
    account = _base_account(option_strike_offset_pct=7.5, option_min_dte=90, option_max_dte=180, option_type="put")
    note = auto_trader._build_trade_note(
        learning_enabled=True,
        forced_sell=None,
        risk_policy="none",
        instrument_mode="leaps",
        account=account,
        side="buy",
        delta_est=0.33,
        iv_est=42.0,
        strategy_name="trend",
    )
    assert "auto-daily-learn" in note
    assert "mode=leaps" in note
    assert "delta=0.33" in note
    assert "iv_rank=42.0" in note
    assert "strategy=trend" in note


def test_choose_side_prioritizes_forced_sell(monkeypatch):
    monkeypatch.setattr(auto_trader.random, "random", lambda: 0.0)
    assert auto_trader._choose_side("AAPL", ["AAPL"]) == "sell"
    assert auto_trader._choose_side(None, ["AAPL"]) == "sell"
    monkeypatch.setattr(auto_trader.random, "random", lambda: 0.99)
    assert auto_trader._choose_side(None, ["AAPL"]) == "buy"


def test_prepare_buy_trade_equity(monkeypatch):
    state = SimpleNamespace(cash=1000.0)
    monkeypatch.setattr(auto_trader, "choose_buy_ticker", lambda *args, **kwargs: "AAPL")
    monkeypatch.setattr(auto_trader, "choose_buy_qty", lambda *args, **kwargs: 2)

    result = auto_trader._prepare_buy_trade(
        account=_base_account(),
        instrument_mode="equity",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=state,
        learning_enabled=False,
        fee=0.0,
    )
    assert result == ("AAPL", 2, 100.0, None, None)


def test_prepare_buy_trade_leaps(monkeypatch):
    state = SimpleNamespace(cash=2000.0)
    account = _base_account(max_contracts_per_trade=2)
    monkeypatch.setattr(auto_trader, "_build_leaps_candidates", lambda *args, **kwargs: [("AAPL", 0.4, 30.0)])
    monkeypatch.setattr(auto_trader.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(auto_trader, "estimate_option_premium", lambda *args, **kwargs: 120.0)
    monkeypatch.setattr(auto_trader, "choose_buy_qty", lambda *args, **kwargs: 4)

    result = auto_trader._prepare_buy_trade(
        account=account,
        instrument_mode="leaps",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={"AAPL": 30.0},
        state=state,
        learning_enabled=True,
        fee=0.0,
    )
    assert result == ("AAPL", 2, 120.0, 0.4, 30.0)


def test_prepare_sell_trade_leaps_forced_sell(monkeypatch):
    state = SimpleNamespace(positions={"AAPL": 5.0})
    monkeypatch.setattr(auto_trader, "choose_sell_qty", lambda *_args, **_kwargs: 4)

    result = auto_trader._prepare_sell_trade(
        can_sell=["AAPL"],
        forced_sell="AAPL",
        prices={"AAPL": 150.0},
        state=state,
        learning_enabled=False,
        instrument_mode="leaps",
    )
    assert result == ("AAPL", 2, 150.0)


def test_build_iv_rank_proxy_handles_empty_and_single(monkeypatch):
    import common.market_data as _mdata

    def fake_fetch_close_series(ticker: str, period: str):
        if ticker == "EMPTY":
            return None
        if ticker == "ONE":
            return pd.Series(range(1, 50), dtype=float)
        return None

    monkeypatch.setattr(_mdata._provider, "fetch_close_series", fake_fetch_close_series)

    assert auto_trader.build_iv_rank_proxy(["EMPTY"]) == {}
    assert auto_trader.build_iv_rank_proxy(["ONE"]) == {"ONE": 50.0}


def test_main_validation_errors(monkeypatch):
    args = SimpleNamespace(
        min_trades=0,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
    with pytest.raises(ValueError, match="min-trades"):
        auto_trader.main()


def test_main_happy_path_dispatches_accounts(monkeypatch, capsys):
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
        tickers_file="trading/trade_universe.txt",
        fee=1.0,
    )

    calls = []

    monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
    monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL", "MSFT"])
    monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {"AAPL": 100.0, "MSFT": 200.0})
    monkeypatch.setattr(auto_trader, "build_iv_rank_proxy", lambda _u: {"AAPL": 40.0})
    monkeypatch.setattr(auto_trader, "ensure_db", lambda: conn)

    def _fake_run_for_account(**kwargs):
        calls.append(kwargs["account_name"])
        return 2

    monkeypatch.setattr(auto_trader, "run_for_account", _fake_run_for_account)

    auto_trader.main()

    assert calls == ["acct1", "acct2"]
    out = capsys.readouterr().out
    assert "acct1: executed 2 trades" in out
    assert "acct2: executed 2 trades" in out
    assert conn.closed is True


def test_choose_sell_ticker_by_risk_stop_and_target(monkeypatch):
    state = SimpleNamespace(avg_cost={"LOSS": 100.0, "WIN": 100.0})
    prices = {"LOSS": 90.0, "WIN": 120.0}

    monkeypatch.setattr(auto_trader.random, "choice", lambda seq: seq[0])

    ticker = auto_trader.choose_sell_ticker_by_risk(
        can_sell=["LOSS", "WIN"],
        prices=prices,
        state=state,
        risk_policy="stop_and_target",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
    )
    assert ticker in {"LOSS", "WIN"}


def test_choose_buy_ticker_learning_and_fallback(monkeypatch):
    state = SimpleNamespace(avg_cost={"A": 100.0, "B": 50.0})
    prices = {"A": 110.0, "B": 40.0}

    monkeypatch.setattr(auto_trader.random, "choice", lambda seq: seq[0])
    assert auto_trader.choose_buy_ticker(["A", "B"], prices, state, learning_enabled=True) == "A"

    # Fallback when no valid scored prices
    assert auto_trader.choose_buy_ticker(["A", "B"], {"A": -1.0}, state, learning_enabled=True) == "A"


def test_choose_sell_ticker_learning(monkeypatch):
    state = SimpleNamespace(avg_cost={"A": 100.0, "B": 100.0})
    prices = {"A": 80.0, "B": 130.0}

    monkeypatch.setattr(auto_trader.random, "choice", lambda seq: seq[0])
    # Learning mode should prefer worst performers (A here)
    assert auto_trader.choose_sell_ticker(["A", "B"], prices, state, learning_enabled=True) == "A"


def test_build_leaps_candidates_filters(monkeypatch):
    account = _base_account()
    prices = {"A": 100.0, "B": 200.0}

    def _fake_allowed(_account, ticker, _price, _iv):
        if ticker == "A":
            return True, 0.4, 25.0
        return False, 0.4, 25.0

    monkeypatch.setattr(auto_trader, "option_candidate_allowed", _fake_allowed)
    candidates = auto_trader._build_leaps_candidates(account, ["A", "B"], prices, {"A": 25.0, "B": 25.0})
    assert candidates == [("A", 0.4, 25.0)]


def test_prepare_buy_trade_returns_none_when_no_candidates(monkeypatch):
    monkeypatch.setattr(auto_trader, "_build_leaps_candidates", lambda *args, **kwargs: [])
    result = auto_trader._prepare_buy_trade(
        account=_base_account(),
        instrument_mode="leaps",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0),
        learning_enabled=True,
        fee=0.0,
    )
    assert result is None


def test_prepare_sell_trade_returns_none_when_invalid_price(monkeypatch):
    monkeypatch.setattr(auto_trader, "choose_sell_ticker", lambda *args, **kwargs: "AAPL")
    result = auto_trader._prepare_sell_trade(
        can_sell=["AAPL"],
        forced_sell=None,
        prices={"AAPL": 0.0},
        state=SimpleNamespace(positions={"AAPL": 3.0}),
        learning_enabled=True,
        instrument_mode="equity",
    )
    assert result is None


def test_run_for_account_executes_buy_and_records_trade(monkeypatch):
    account = _base_account(learning_enabled=1, id=42)
    state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

    monkeypatch.setattr(auto_trader, "get_account", lambda _conn, _name: account)
    monkeypatch.setattr(auto_trader, "load_trades", lambda _conn, _id: [])
    monkeypatch.setattr(auto_trader, "compute_account_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(auto_trader.random, "randint", lambda a, b: 1)  # target trades = 1
    monkeypatch.setattr(auto_trader, "_choose_side", lambda *_args, **_kwargs: "buy")
    monkeypatch.setattr(auto_trader, "_prepare_buy_trade", lambda *_args, **_kwargs: ("AAPL", 2, 101.0, None, None))
    monkeypatch.setattr(auto_trader, "utc_now_iso", lambda: "2026-03-14T00:00:00Z")

    calls = []
    monkeypatch.setattr(auto_trader, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

    executed = auto_trader.run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )
    assert executed == 1
    assert calls[0]["side"] == "buy"
    assert calls[0]["ticker"] == "AAPL"
    assert calls[0]["note"].startswith("auto-daily-learn")
    assert "strategy=trend" in calls[0]["note"]


def test_run_for_account_forced_sell_note_includes_risk(monkeypatch):
    account = _base_account(learning_enabled=0, id=7, risk_policy="fixed_stop", stop_loss_pct=5.0)
    state = SimpleNamespace(cash=1000.0, positions={"AAPL": 3.0}, avg_cost={"AAPL": 100.0})

    monkeypatch.setattr(auto_trader, "get_account", lambda _conn, _name: account)
    monkeypatch.setattr(auto_trader, "load_trades", lambda _conn, _id: [])
    monkeypatch.setattr(auto_trader, "compute_account_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(auto_trader.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(auto_trader, "choose_sell_ticker_by_risk", lambda *_args, **_kwargs: "AAPL")
    monkeypatch.setattr(auto_trader, "_prepare_sell_trade", lambda *_args, **_kwargs: ("AAPL", 1, 95.0))
    monkeypatch.setattr(auto_trader, "utc_now_iso", lambda: "2026-03-14T00:00:00Z")

    calls = []
    monkeypatch.setattr(auto_trader, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

    executed = auto_trader.run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 95.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )
    assert executed == 1
    assert calls[0]["side"] == "sell"
    assert "risk=fixed_stop" in calls[0]["note"]


def test_rotate_account_if_due_updates_state(monkeypatch):
    account_before = _base_account(
        id=9,
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )

    class _Conn:
        def __init__(self):
            self.updated = None
            self.committed = False

        def execute(self, _sql, params):
            self.updated = params

        def commit(self):
            self.committed = True

    conn = _Conn()
    account_after = _base_account(
        id=9,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )

    monkeypatch.setattr(auto_trader, "get_account", lambda _conn, _name: account_after)
    out = auto_trader._rotate_account_if_due(conn, "acct", account_before, "2026-03-17T00:00:00Z")

    assert conn.committed is True
    assert conn.updated is not None
    assert conn.updated[0] == "mean_reversion"
    assert out["strategy"] == "mean_reversion"


def test_run_for_account_uses_rotated_active_strategy(monkeypatch):
    initial_account = _base_account(
        id=11,
        strategy="trend",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )
    rotated_account = _base_account(
        id=11,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )
    state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

    monkeypatch.setattr(auto_trader, "get_account", lambda _conn, _name: initial_account)
    monkeypatch.setattr(auto_trader, "_rotate_account_if_due", lambda _conn, _name, _acct, _now: rotated_account)
    monkeypatch.setattr(auto_trader, "load_trades", lambda _conn, _id: [])
    monkeypatch.setattr(auto_trader, "compute_account_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(auto_trader.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(auto_trader, "_choose_side", lambda _forced, _sell, strategy_name=None: "buy" if strategy_name == "mean_reversion" else "sell")
    monkeypatch.setattr(auto_trader, "_prepare_buy_trade", lambda *_args, **_kwargs: ("AAPL", 1, 100.0, None, None))
    monkeypatch.setattr(auto_trader, "utc_now_iso", lambda: "2026-03-17T00:00:00Z")

    calls = []
    monkeypatch.setattr(auto_trader, "record_trade", lambda _conn, **kwargs: calls.append(kwargs))

    executed = auto_trader.run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )
    assert executed == 1
    assert calls[0]["side"] == "buy"
    assert "strategy=mean_reversion" in calls[0]["note"]


def test_main_additional_validation_paths(monkeypatch):
    args = SimpleNamespace(
        min_trades=2,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
    with pytest.raises(ValueError, match="max-trades"):
        auto_trader.main()

    args.max_trades = 2
    args.accounts = "  ,   "
    with pytest.raises(ValueError, match="No accounts"):
        auto_trader.main()


def test_main_empty_universe_and_no_prices(monkeypatch):
    args = SimpleNamespace(
        min_trades=1,
        max_trades=1,
        seed=None,
        accounts="acct1",
        tickers_file="trading/trade_universe.txt",
        fee=0.0,
    )
    monkeypatch.setattr(auto_trader, "parse_args", lambda: args)

    monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: [])
    with pytest.raises(ValueError, match="Ticker universe is empty"):
        auto_trader.main()

    monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {})
    with pytest.raises(ValueError, match="Could not fetch any prices"):
        auto_trader.main()


def test_main_closes_connection_when_run_for_account_fails(monkeypatch):
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
        tickers_file="trading/trade_universe.txt",
        fee=0.0,
    )

    monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
    monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL"])
    monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {"AAPL": 100.0})
    monkeypatch.setattr(auto_trader, "build_iv_rank_proxy", lambda _u: {})
    monkeypatch.setattr(auto_trader, "ensure_db", lambda: conn)
    monkeypatch.setattr(auto_trader, "run_for_account", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        auto_trader.main()

    assert conn.closed is True
