from types import SimpleNamespace

import trading.domain.auto_trader_policy as auto_trader_policy
import trading.services.trade_execution_service as trade_execution_service


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
    }
    base.update(overrides)
    return base


def test_build_leaps_candidates_filters() -> None:
    account = _base_account()
    prices = {"A": 100.0, "B": 200.0}

    def _fake_allowed(_account, ticker, _price, _iv):
        if ticker == "A":
            return True, 0.4, 25.0
        return False, 0.4, 25.0

    candidates = trade_execution_service.build_leaps_candidates(
        account,
        ["A", "B"],
        prices,
        {"A": 25.0, "B": 25.0},
        option_candidate_allowed_fn=_fake_allowed,
    )
    assert candidates == [("A", 0.4, 25.0)]


def test_prepare_buy_trade_equity() -> None:
    state = SimpleNamespace(cash=1000.0)
    result = trade_execution_service.prepare_buy_trade(
        account=_base_account(),
        instrument_mode="equity",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=state,
        learning_enabled=False,
        fee=0.0,
        build_leaps_candidates_fn=lambda *_args, **_kwargs: [],
        estimate_option_premium_fn=auto_trader_policy.estimate_option_premium,
        choose_buy_qty_fn=lambda *_args, **_kwargs: 2,
        apply_leaps_buy_qty_limits_fn=auto_trader_policy.apply_leaps_buy_qty_limits,
        choose_buy_ticker_fn=lambda *_args, **_kwargs: "AAPL",
    )
    assert result == ("AAPL", 2, 100.0, None, None)


def test_prepare_buy_trade_leaps(monkeypatch) -> None:
    state = SimpleNamespace(cash=2000.0)
    account = _base_account(max_contracts_per_trade=2)
    monkeypatch.setattr(trade_execution_service.random, "choice", lambda seq: seq[0])

    result = trade_execution_service.prepare_buy_trade(
        account=account,
        instrument_mode="leaps",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={"AAPL": 30.0},
        state=state,
        learning_enabled=True,
        fee=0.0,
        build_leaps_candidates_fn=lambda *_args, **_kwargs: [("AAPL", 0.4, 30.0)],
        estimate_option_premium_fn=lambda *_args, **_kwargs: 120.0,
        choose_buy_qty_fn=lambda *_args, **_kwargs: 4,
        apply_leaps_buy_qty_limits_fn=auto_trader_policy.apply_leaps_buy_qty_limits,
        choose_buy_ticker_fn=auto_trader_policy.choose_buy_ticker,
    )
    assert result == ("AAPL", 2, 120.0, 0.4, 30.0)


def test_prepare_sell_trade_leaps_forced_sell() -> None:
    state = SimpleNamespace(positions={"AAPL": 5.0})

    result = trade_execution_service.prepare_sell_trade(
        can_sell=["AAPL"],
        forced_sell="AAPL",
        prices={"AAPL": 150.0},
        state=state,
        learning_enabled=False,
        instrument_mode="leaps",
        choose_sell_ticker_fn=auto_trader_policy.choose_sell_ticker,
        choose_sell_qty_fn=lambda *_args, **_kwargs: 4,
    )
    assert result == ("AAPL", 2, 150.0)


def test_prepare_buy_trade_returns_none_when_no_candidates() -> None:
    result = trade_execution_service.prepare_buy_trade(
        account=_base_account(),
        instrument_mode="leaps",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0),
        learning_enabled=True,
        fee=0.0,
        build_leaps_candidates_fn=lambda *_args, **_kwargs: [],
        estimate_option_premium_fn=auto_trader_policy.estimate_option_premium,
        choose_buy_qty_fn=auto_trader_policy.choose_buy_qty,
        apply_leaps_buy_qty_limits_fn=auto_trader_policy.apply_leaps_buy_qty_limits,
        choose_buy_ticker_fn=auto_trader_policy.choose_buy_ticker,
    )
    assert result is None


def test_prepare_sell_trade_returns_none_when_invalid_price() -> None:
    result = trade_execution_service.prepare_sell_trade(
        can_sell=["AAPL"],
        forced_sell=None,
        prices={"AAPL": 0.0},
        state=SimpleNamespace(positions={"AAPL": 3.0}),
        learning_enabled=True,
        instrument_mode="equity",
        choose_sell_ticker_fn=lambda *_args, **_kwargs: "AAPL",
        choose_sell_qty_fn=auto_trader_policy.choose_sell_qty,
    )
    assert result is None


def test_prepare_trade_selection_uses_forced_sell_path() -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0})
    account = _base_account()

    selection = trade_execution_service.prepare_trade_selection(
        account=account,
        active_strategy="trend",
        state=state,
        can_sell=["AAPL"],
        forced_sell="AAPL",
        universe=["AAPL"],
        prices={"AAPL": 95.0},
        iv_rank_proxy={},
        learning_enabled=False,
        instrument_mode="equity",
        fee=0.0,
        choose_side_fn=lambda *_args, **_kwargs: "sell",
        prepare_buy_trade_fn=lambda *_args, **_kwargs: None,
        prepare_sell_trade_fn=lambda *_args, **_kwargs: ("AAPL", 1, 95.0),
    )

    assert selection == ("sell", "AAPL", 1, 95.0, None, None)


def test_refresh_account_state_delegates_to_load_and_compute() -> None:
    account = _base_account(initial_cash=1234.0, id=77)
    seen: dict[str, object] = {}

    def _fake_load_trades(_conn, account_id):
        seen["account_id"] = account_id
        return []

    def _fake_compute(initial_cash, trades):
        seen["initial_cash"] = initial_cash
        seen["trades"] = trades
        return "STATE"

    out = trade_execution_service.refresh_account_state(
        conn=object(),
        account=account,
        compute_account_state_fn=_fake_compute,
        load_trades_fn=_fake_load_trades,
    )
    assert out == "STATE"
    assert seen == {"account_id": 77, "initial_cash": 1234.0, "trades": []}