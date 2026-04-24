from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

import trading.domain.auto_trader_policy as auto_trader_policy
import trading.services.auto_trading.execution as trade_execution_service
from tests.support import make_auto_trading_account


def test_build_leaps_candidates_filters() -> None:
    account = make_auto_trading_account()
    prices = {"A": 100.0, "B": 200.0}

    def _fake_allowed(_account, ticker, _price, _iv, *, estimate_delta_fn):
        assert estimate_delta_fn is auto_trader_policy.estimate_delta
        if ticker == "A":
            return True, 0.4, 25.0
        return False, 0.4, 25.0

    with patch.object(trade_execution_service.auto_trader_policy, "option_candidate_allowed", _fake_allowed):
        candidates = trade_execution_service.build_leaps_candidates(
            account,
            ["A", "B"],
            prices,
            {"A": 25.0, "B": 25.0},
        )
    assert candidates == [("A", 0.4, 25.0)]


def test_prepare_buy_trade_equity() -> None:
    state = SimpleNamespace(cash=1000.0)
    choose_buy_qty = Mock(return_value=2)
    choose_buy_ticker = Mock(return_value="AAPL")
    with patch.object(trade_execution_service.auto_trader_policy, "choose_buy_qty", choose_buy_qty), patch.object(
        trade_execution_service.auto_trader_policy,
        "choose_buy_ticker",
        choose_buy_ticker,
    ):
        result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="equity",
            universe=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=state,
            learning_enabled=False,
            fee=0.0,
        )
    assert result == ("AAPL", 2, 100.0, None, None)
    choose_buy_ticker.assert_called_once()
    choose_buy_qty.assert_called_once()


def test_prepare_buy_trade_leaps(monkeypatch) -> None:
    state = SimpleNamespace(cash=2000.0)
    account = make_auto_trading_account(max_contracts_per_trade=2)
    monkeypatch.setattr(trade_execution_service.random, "choice", lambda seq: seq[0])
    build_candidates = Mock(return_value=[("AAPL", 0.4, 30.0)])
    with patch.object(trade_execution_service, "build_leaps_candidates", build_candidates), patch.object(
        trade_execution_service.auto_trader_policy,
        "estimate_option_premium",
        Mock(return_value=120.0),
    ), patch.object(
        trade_execution_service.auto_trader_policy,
        "choose_buy_qty",
        Mock(return_value=4),
    ):
        result = trade_execution_service.prepare_buy_trade(
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
    build_candidates.assert_called_once()


def test_prepare_sell_trade_leaps_forced_sell() -> None:
    state = SimpleNamespace(positions={"AAPL": 5.0})
    choose_sell_qty = Mock(return_value=4)
    with patch.object(trade_execution_service.auto_trader_policy, "choose_sell_qty", choose_sell_qty):
        result = trade_execution_service.prepare_sell_trade(
            can_sell=["AAPL"],
            forced_sell="AAPL",
            prices={"AAPL": 150.0},
            state=state,
            learning_enabled=False,
            instrument_mode="leaps",
        )
    assert result == ("AAPL", 2, 150.0)
    choose_sell_qty.assert_called_once_with(5.0)


def test_prepare_buy_trade_returns_none_when_no_candidates() -> None:
    with patch.object(trade_execution_service, "build_leaps_candidates", Mock(return_value=[])):
        result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="leaps",
            universe=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0),
            learning_enabled=True,
            fee=0.0,
        )
    assert result is None


def test_prepare_sell_trade_returns_none_when_invalid_price() -> None:
    choose_sell_ticker = Mock(return_value="AAPL")
    with patch.object(trade_execution_service.auto_trader_policy, "choose_sell_ticker", choose_sell_ticker):
        result = trade_execution_service.prepare_sell_trade(
            can_sell=["AAPL"],
            forced_sell=None,
            prices={"AAPL": 0.0},
            state=SimpleNamespace(positions={"AAPL": 3.0}),
            learning_enabled=True,
            instrument_mode="equity",
        )
    assert result is None
    choose_sell_ticker.assert_called_once()


def test_prepare_trade_selection_uses_forced_sell_path() -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0})
    account = make_auto_trading_account()
    choose_side = Mock(return_value="sell")
    prepare_sell_trade = Mock(return_value=("AAPL", 1, 95.0))

    with patch.object(trade_execution_service.auto_trader_policy, "choose_side", choose_side), patch.object(
        trade_execution_service,
        "prepare_sell_trade",
        prepare_sell_trade,
    ):
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
        )

    assert selection == ("sell", "AAPL", 1, 95.0, None, None)
    choose_side.assert_called_once_with("AAPL", ["AAPL"], "trend")
    prepare_sell_trade.assert_called_once()


def test_refresh_account_state_delegates_to_load_and_compute(monkeypatch) -> None:
    account = make_auto_trading_account(initial_cash=1234.0, id=77)
    seen: dict[str, object] = {}

    def _fake_load_trades(_conn, account_id):
        seen["account_id"] = account_id
        return []

    def _fake_compute(initial_cash, trades):
        seen["initial_cash"] = initial_cash
        seen["trades"] = trades
        return "STATE"

    monkeypatch.setattr(trade_execution_service, "list_account_trades", _fake_load_trades)
    monkeypatch.setattr(trade_execution_service, "compute_account_state", _fake_compute)

    out = trade_execution_service.refresh_account_state(conn=object(), account=account)
    assert out == "STATE"
    assert seen == {"account_id": 77, "initial_cash": 1234.0, "trades": []}
