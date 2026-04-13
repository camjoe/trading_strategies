from types import SimpleNamespace

import pytest

import trading.domain.auto_trader_policy as auto_trader_policy


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


def test_choose_qty_helpers(monkeypatch) -> None:
    monkeypatch.setattr(auto_trader_policy.random, "randint", lambda a, b: b)
    assert auto_trader_policy.choose_buy_qty(cash=10.0, price=11.0, fee=0.0) == 0
    assert auto_trader_policy.choose_buy_qty(cash=100.0, price=10.0, fee=0.0) == 5
    assert auto_trader_policy.choose_sell_qty(position_qty=0.2) == 0
    assert auto_trader_policy.choose_sell_qty(position_qty=9.0) == 5


def test_estimate_helpers_boundaries() -> None:
    assert auto_trader_policy.estimate_delta(0.0) == pytest.approx(0.55)
    assert auto_trader_policy.estimate_delta(1000.0) == pytest.approx(0.05)
    premium = auto_trader_policy.estimate_option_premium(
        underlying_price=100.0,
        delta_est=0.4,
        min_dte=100,
        max_dte=200,
    )
    assert premium > 0.5


def test_option_candidate_allowed_with_delta_and_iv_filters() -> None:
    account = _base_account(target_delta_min=0.6)
    ok, _, _ = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        100.0,
        {"AAPL": 50.0},
        estimate_delta_fn=auto_trader_policy.estimate_delta,
    )
    assert ok is False

    account = _base_account(iv_rank_min=20.0)
    ok, _, iv_rank = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        100.0,
        {},
        estimate_delta_fn=auto_trader_policy.estimate_delta,
    )
    assert ok is False
    assert iv_rank == -1.0

    account = _base_account(target_delta_min=0.1, target_delta_max=0.9, iv_rank_min=10.0, iv_rank_max=90.0)
    ok, delta, iv_rank = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        100.0,
        {"AAPL": 50.0},
        estimate_delta_fn=auto_trader_policy.estimate_delta,
    )
    assert ok is True
    assert 0.0 <= delta <= 1.0
    assert iv_rank == 50.0


def test_apply_leaps_buy_qty_limits() -> None:
    account = _base_account(max_contracts_per_trade=3, max_premium_per_trade=250.0)
    qty = auto_trader_policy.apply_leaps_buy_qty_limits(qty=5, option_price=100.0, account=account)
    assert qty == 2


def test_build_trade_note_for_leaps_buy() -> None:
    account = _base_account(option_strike_offset_pct=7.5, option_min_dte=90, option_max_dte=180, option_type="put")
    note = auto_trader_policy.build_trade_note(
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
    assert "selection=heuristic-exploration" in note
    assert "mode=leaps" in note
    assert "delta=0.33" in note
    assert "iv_rank=42.0" in note
    assert "strategy=trend" in note


def test_choose_side_prioritizes_forced_sell(monkeypatch) -> None:
    monkeypatch.setattr(auto_trader_policy.random, "random", lambda: 0.0)
    assert auto_trader_policy.choose_side("AAPL", ["AAPL"]) == "sell"
    assert auto_trader_policy.choose_side(None, ["AAPL"]) == "sell"
    monkeypatch.setattr(auto_trader_policy.random, "random", lambda: 0.99)
    assert auto_trader_policy.choose_side(None, ["AAPL"]) == "buy"


def test_choose_sell_ticker_by_risk_stop_and_target(monkeypatch) -> None:
    state = SimpleNamespace(avg_cost={"LOSS": 100.0, "WIN": 100.0})
    prices = {"LOSS": 90.0, "WIN": 120.0}

    monkeypatch.setattr(auto_trader_policy.random, "choice", lambda seq: seq[0])

    ticker = auto_trader_policy.choose_sell_ticker_by_risk(
        can_sell=["LOSS", "WIN"],
        prices=prices,
        state=state,
        risk_policy="stop_and_target",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
    )
    assert ticker in {"LOSS", "WIN"}


def test_choose_buy_ticker_learning_and_fallback(monkeypatch) -> None:
    state = SimpleNamespace(avg_cost={"A": 100.0, "B": 50.0})
    prices = {"A": 110.0, "B": 40.0}

    monkeypatch.setattr(auto_trader_policy.random, "choice", lambda seq: seq[0])
    assert auto_trader_policy.choose_buy_ticker(["A", "B"], prices, state, learning_enabled=True) == "A"
    assert auto_trader_policy.choose_buy_ticker(["A", "B"], {"A": -1.0}, state, learning_enabled=True) == "A"


def test_choose_sell_ticker_learning(monkeypatch) -> None:
    state = SimpleNamespace(avg_cost={"A": 100.0, "B": 100.0})
    prices = {"A": 80.0, "B": 130.0}

    monkeypatch.setattr(auto_trader_policy.random, "choice", lambda seq: seq[0])
    assert auto_trader_policy.choose_sell_ticker(["A", "B"], prices, state, learning_enabled=True) == "A"
