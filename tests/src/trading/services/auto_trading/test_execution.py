from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

import trading.services.auto_trading.execution as trade_execution_service
from tests.src.trading.services.auto_trading.factories import make_auto_trading_account


def test_resolve_strategy_params_returns_registry_defaults() -> None:
    account = make_auto_trading_account()

    params = trade_execution_service.resolve_strategy_params(account, "trend")

    assert params == {"fast_window": 10, "slow_window": 20}


def test_resolve_strategy_params_returns_a_copy() -> None:
    account = make_auto_trading_account()

    params = trade_execution_service.resolve_strategy_params(account, "trend")
    params["fast_window"] = 1

    assert trade_execution_service.resolve_strategy_params(account, "trend")["fast_window"] == 10


def test_prepare_buy_trade_equity() -> None:
    state = SimpleNamespace(cash=1000.0)
    choose_buy_qty = Mock(return_value=2)
    with patch.object(trade_execution_service.auto_trader_policy, "choose_buy_qty", choose_buy_qty):
        result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="equity",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=state,
            fee=0.0,
        )
    assert result == ("AAPL", 2, 100.0, None, None)
    choose_buy_qty.assert_called_once()


def test_prepare_buy_trade_leaps() -> None:
    state = SimpleNamespace(cash=2000.0)
    account = make_auto_trading_account(max_contracts_per_trade=2)
    with (
        patch.object(
            trade_execution_service.auto_trader_policy,
            "option_candidate_allowed",
            Mock(return_value=(True, 0.4, 30.0)),
        ),
        patch.object(
            trade_execution_service.auto_trader_policy,
            "estimate_option_premium",
            Mock(return_value=120.0),
        ),
        patch.object(
            trade_execution_service.auto_trader_policy,
            "choose_buy_qty",
            Mock(return_value=4),
        ),
    ):
        result = trade_execution_service.prepare_buy_trade(
            account=account,
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={"AAPL": 30.0},
            state=state,
            fee=0.0,
        )
    assert result == ("AAPL", 2, 120.0, 0.4, 30.0)


def test_prepare_buy_trade_leaps_skips_disallowed_candidate_and_uses_next() -> None:
    state = SimpleNamespace(cash=2000.0)

    def _fake_allowed(_account, ticker, _iv):
        if ticker == "MSFT":
            return True, 0.4, 25.0
        return False, 0.4, 25.0

    with (
        patch.object(trade_execution_service.auto_trader_policy, "option_candidate_allowed", _fake_allowed),
        patch.object(
            trade_execution_service.auto_trader_policy,
            "estimate_option_premium",
            Mock(return_value=100.0),
        ),
        patch.object(trade_execution_service.auto_trader_policy, "choose_buy_qty", Mock(return_value=1)),
    ):
        result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="leaps",
            buy_candidates=["AAPL", "MSFT"],
            prices={"AAPL": 100.0, "MSFT": 200.0},
            iv_rank_proxy={"AAPL": 25.0, "MSFT": 25.0},
            state=state,
            fee=0.0,
        )
    assert result is not None
    assert result[0] == "MSFT"


def test_prepare_sell_trade_leaps_forced_sell() -> None:
    state = SimpleNamespace(positions={"AAPL": 5.0})
    choose_sell_qty = Mock(return_value=4)
    with patch.object(trade_execution_service.auto_trader_policy, "choose_sell_qty", choose_sell_qty):
        result = trade_execution_service.prepare_sell_trade(
            sell_candidates=[],
            forced_sell="AAPL",
            prices={"AAPL": 150.0},
            state=state,
            instrument_mode="leaps",
        )
    assert result == ("AAPL", 2, 150.0)
    choose_sell_qty.assert_called_once_with(5.0)


def test_prepare_buy_trade_returns_none_when_no_candidates() -> None:
    result = trade_execution_service.prepare_buy_trade(
        account=make_auto_trading_account(),
        instrument_mode="leaps",
        buy_candidates=[],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0),
        fee=0.0,
    )
    assert result is None


def test_prepare_sell_trade_returns_none_when_invalid_price() -> None:
    result = trade_execution_service.prepare_sell_trade(
        sell_candidates=["AAPL"],
        forced_sell=None,
        prices={"AAPL": 0.0},
        state=SimpleNamespace(positions={"AAPL": 3.0}),
        instrument_mode="equity",
    )
    assert result is None


def test_prepare_sell_trade_returns_none_when_qty_non_positive() -> None:
    choose_sell_qty = Mock(return_value=0)
    with patch.object(trade_execution_service.auto_trader_policy, "choose_sell_qty", choose_sell_qty):
        result = trade_execution_service.prepare_sell_trade(
            sell_candidates=["AAPL"],
            forced_sell=None,
            prices={"AAPL": 100.0},
            state=SimpleNamespace(positions={"AAPL": 3.0}),
            instrument_mode="equity",
        )
    assert result is None
    choose_sell_qty.assert_called_once_with(3.0)


def test_prepare_sell_trade_equity_returns_qty_without_leaps_cap() -> None:
    choose_sell_qty = Mock(return_value=4)
    with patch.object(trade_execution_service.auto_trader_policy, "choose_sell_qty", choose_sell_qty):
        result = trade_execution_service.prepare_sell_trade(
            sell_candidates=["AAPL"],
            forced_sell=None,
            prices={"AAPL": 100.0},
            state=SimpleNamespace(positions={"AAPL": 4.0}),
            instrument_mode="equity",
        )
    assert result == ("AAPL", 4, 100.0)


def test_prepare_buy_trade_returns_none_when_equity_price_missing() -> None:
    result = trade_execution_service.prepare_buy_trade(
        account=make_auto_trading_account(),
        instrument_mode="equity",
        buy_candidates=["AAPL"],
        prices={},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0),
        fee=0.0,
    )
    assert result is None


def test_position_mark_price_prefers_leaps_trade_price_then_avg_cost() -> None:
    assert (
        trade_execution_service._position_mark_price(
            "AAPL",
            prices={"AAPL": 150.0},
            avg_cost={"AAPL": 120.0},
            instrument_mode="leaps",
            trade_price=130.0,
        )
        == 130.0
    )
    assert (
        trade_execution_service._position_mark_price(
            "AAPL",
            prices={"AAPL": 150.0},
            avg_cost={"AAPL": 120.0},
            instrument_mode="leaps",
        )
        == 120.0
    )


def test_estimate_portfolio_equity_skips_non_positive_positions_and_marks() -> None:
    state = SimpleNamespace(
        cash=500.0,
        positions={"AAPL": 2.0, "MSFT": -1.0, "NVDA": 1.0},
        avg_cost={"AAPL": 110.0, "NVDA": 50.0},
    )
    # AAPL uses market price, NVDA uses avg cost because market price <= 0, MSFT is ignored (qty <= 0).
    equity = trade_execution_service._estimate_portfolio_equity(
        state,
        prices={"AAPL": 100.0, "NVDA": 0.0},
        instrument_mode="equity",
    )
    assert equity == 500.0 + (2.0 * 100.0) + (1.0 * 50.0)


def test_estimate_portfolio_equity_skips_position_when_mark_price_non_positive(monkeypatch) -> None:
    state = SimpleNamespace(cash=500.0, positions={"AAPL": 2.0}, avg_cost={"AAPL": 110.0})
    monkeypatch.setattr(trade_execution_service, "_position_mark_price", lambda *_a, **_k: 0.0)
    equity = trade_execution_service._estimate_portfolio_equity(
        state,
        prices={"AAPL": 100.0},
        instrument_mode="equity",
    )
    assert equity == 500.0


def test_current_position_value_returns_zero_when_no_position_and_uses_helper_when_present(monkeypatch) -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0})
    assert (
        trade_execution_service._current_position_value(
            SimpleNamespace(positions={}, avg_cost={}),
            "AAPL",
            prices={"AAPL": 100.0},
            instrument_mode="equity",
            trade_price=100.0,
        )
        == 0.0
    )
    monkeypatch.setattr(trade_execution_service, "_position_mark_price", lambda *_a, **_k: 75.0)
    assert (
        trade_execution_service._current_position_value(
            state,
            "AAPL",
            prices={"AAPL": 100.0},
            instrument_mode="equity",
            trade_price=100.0,
        )
        == 150.0
    )


def test_prepare_buy_trade_returns_none_when_choose_buy_qty_non_positive() -> None:
    with patch.object(trade_execution_service.auto_trader_policy, "choose_buy_qty", Mock(return_value=0)):
        result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="equity",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0),
            fee=0.0,
        )
    assert result is None


def test_prepare_buy_trade_leaps_returns_none_for_invalid_option_price_and_qty_limits() -> None:
    with (
        patch.object(
            trade_execution_service.auto_trader_policy,
            "option_candidate_allowed",
            Mock(return_value=(True, 0.4, 20.0)),
        ),
        patch.object(trade_execution_service.auto_trader_policy, "estimate_option_premium", Mock(return_value=50.0)),
        patch.object(trade_execution_service.auto_trader_policy, "choose_buy_qty", Mock(return_value=3)),
        patch.object(trade_execution_service.auto_trader_policy, "apply_leaps_buy_qty_limits", Mock(return_value=0)),
    ):
        invalid_price_result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0),
            fee=0.0,
        )
        limited_qty_result = trade_execution_service.prepare_buy_trade(
            account=make_auto_trading_account(),
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0),
            fee=0.0,
        )
    assert invalid_price_result is None
    assert limited_qty_result is None


def _rising_history(length: int = 40) -> "trade_execution_service.pd.Series":
    return trade_execution_service.pd.Series([float(i) for i in range(1, length + 1)])


def _sell_history() -> "trade_execution_service.pd.Series":
    return trade_execution_service.pd.Series([100.0] * 39 + [90.0])


def test_select_signal_trade_candidates_buy_and_sell_split_by_holdings() -> None:
    histories = {"UP": _rising_history(), "DOWN": _sell_history(), "HELD_UP": _rising_history()}

    buys, sells = trade_execution_service.select_signal_trade_candidates(
        "trend",
        {"fast_window": 10, "slow_window": 20},
        ["UP", "DOWN", "HELD_UP"],
        histories,
        positions={"DOWN": 2.0, "HELD_UP": 1.0},
    )

    # UP signals buy and is not held; HELD_UP signals buy but is held → excluded.
    # DOWN signals sell and is held → sell candidate.
    assert buys == ["UP"]
    assert sells == ["DOWN"]


def test_select_signal_trade_candidates_missing_history_is_hold() -> None:
    buys, sells = trade_execution_service.select_signal_trade_candidates(
        "trend",
        {"fast_window": 10, "slow_window": 20},
        ["NOHIST", "EMPTY"],
        {"EMPTY": trade_execution_service.pd.Series(dtype=float)},
        positions={},
    )
    assert buys == []
    assert sells == []


def test_prepare_trade_selection_uses_forced_sell_path() -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0})
    account = make_auto_trading_account()
    prepare_sell_trade = Mock(return_value=("AAPL", 1, 95.0))

    with patch.object(trade_execution_service, "prepare_sell_trade", prepare_sell_trade):
        selection = trade_execution_service.prepare_trade_selection(
            account=account,
            active_strategy="trend",
            state=state,
            forced_sell="AAPL",
            universe=["AAPL"],
            prices={"AAPL": 95.0},
            histories={},
            iv_rank_proxy={},
            instrument_mode="equity",
            fee=0.0,
        )

    assert selection == ("sell", "AAPL", 1, 95.0, None, None)
    prepare_sell_trade.assert_called_once()


def test_prepare_trade_selection_returns_none_when_nothing_signals() -> None:
    # Flat history → hold for the trend strategy; no forced sell → no trade at all.
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_trade_selection(
        account=make_auto_trading_account(),
        active_strategy="trend",
        state=state,
        forced_sell=None,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        histories={"AAPL": trade_execution_service.pd.Series([100.0] * 40)},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
    )
    assert selection is None


def test_prepare_trade_selection_buys_on_buy_signal() -> None:
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_trade_selection(
        account=make_auto_trading_account(),
        active_strategy="trend",
        state=state,
        forced_sell=None,
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        histories={"AAPL": _rising_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
    )
    assert selection is not None
    side, ticker, qty, trade_price, _delta, _iv = selection
    assert (side, ticker, trade_price) == ("buy", "AAPL", 10.0)
    assert qty >= 1


def test_prepare_trade_selection_sells_on_sell_signal_for_held_ticker(monkeypatch) -> None:
    monkeypatch.setattr(trade_execution_service.auto_trader_policy, "choose_sell_qty", lambda qty: int(qty))
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0}, cash=0.0)
    selection = trade_execution_service.prepare_trade_selection(
        account=make_auto_trading_account(),
        active_strategy="trend",
        state=state,
        forced_sell=None,
        universe=["AAPL"],
        prices={"AAPL": 90.0},
        histories={"AAPL": _sell_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
    )
    assert selection == ("sell", "AAPL", 2, 90.0, None, None)


def test_prepare_trade_selection_unknown_strategy_holds() -> None:
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_trade_selection(
        account=make_auto_trading_account(),
        active_strategy="totally_unknown_xyz",
        state=state,
        forced_sell=None,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        histories={"AAPL": _rising_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
    )
    assert selection is None


def test_prepare_trade_selection_returns_buy_selection_with_estimates() -> None:
    with (
        patch.object(
            trade_execution_service,
            "select_signal_trade_candidates",
            Mock(return_value=(["AAPL"], [])),
        ),
        patch.object(
            trade_execution_service,
            "prepare_buy_trade",
            Mock(return_value=("AAPL", 2, 100.0, 0.35, 22.0)),
        ),
    ):
        selection = trade_execution_service.prepare_trade_selection(
            account=make_auto_trading_account(),
            active_strategy="trend",
            state=SimpleNamespace(positions={}, avg_cost={}, cash=1000.0),
            forced_sell=None,
            universe=["AAPL"],
            prices={"AAPL": 100.0},
            histories={"AAPL": _rising_history()},
            iv_rank_proxy={},
            instrument_mode="equity",
            fee=0.0,
        )
    assert selection == ("buy", "AAPL", 2, 100.0, 0.35, 22.0)


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


class _StubBundle:
    def __init__(self, features: dict[str, float] | None) -> None:
        self._features = features

    def to_feature_row(self):
        if self._features is None:
            return None
        return trade_execution_service.pd.DataFrame([self._features])


def test_build_feature_history_fn_returns_none_for_non_alternative_styles() -> None:
    fetchers = SimpleNamespace(fetch_policy=Mock(), fetch_news=Mock(), fetch_social=Mock())
    feature_history_for = trade_execution_service.build_feature_history_fn(fetchers)

    assert feature_history_for("trend", "AAPL") is None
    fetchers.fetch_policy.assert_not_called()
    fetchers.fetch_news.assert_not_called()


def test_build_feature_history_fn_uses_matching_fetcher_for_alternative_strategy() -> None:
    bundle = _StubBundle({"news_sentiment_score": 0.4, "news_headline_count": 5.0})
    fetchers = SimpleNamespace(fetch_policy=Mock(), fetch_news=Mock(return_value=bundle), fetch_social=None)
    feature_history_for = trade_execution_service.build_feature_history_fn(fetchers)

    frame = feature_history_for("news_sentiment", "AAPL")

    assert frame is not None
    assert frame.iloc[-1]["news_sentiment_score"] == 0.4
    fetchers.fetch_news.assert_called_once_with("AAPL")
    # social fetcher is None → social strategy safely degrades to no features
    assert feature_history_for("social_trend_rotation", "AAPL") is None


def test_build_feature_history_fn_swallows_fetcher_errors_and_unknown_strategies() -> None:
    fetchers = SimpleNamespace(fetch_policy=Mock(side_effect=RuntimeError("boom")), fetch_news=None, fetch_social=None)
    feature_history_for = trade_execution_service.build_feature_history_fn(fetchers)

    assert feature_history_for("policy_regime", "AAPL") is None
    assert feature_history_for("unknown_strategy_xyz", "AAPL") is None
    assert trade_execution_service.build_feature_history_fn(None)("news_sentiment", "AAPL") is None


def test_run_for_account_breaks_when_submission_window_closes_mid_loop(monkeypatch) -> None:
    account = make_auto_trading_account(id=1, learning_enabled=0, risk_policy="none", instrument_mode="equity")
    now_values = iter(["2026-03-14T14:00:00Z", "2026-03-14T20:01:00Z"])
    monkeypatch.setattr(
        trade_execution_service,
        "refresh_account_state",
        lambda _conn, _account: SimpleNamespace(positions={}),
    )
    monkeypatch.setattr(
        trade_execution_service.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    record_trade = Mock()

    executed = trade_execution_service.run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=2,
        max_trades=2,
        fee=0.0,
        get_account_fn=lambda _conn, _name: account,
        utc_now_iso_fn=lambda: next(now_values),
        rotate_account_if_due_fn=lambda _conn, _name, acc, _now: acc,
        record_prepared_trade_fn=record_trade,
        is_submission_window_open_fn=lambda now_iso: now_iso.endswith("14:00:00Z"),
    )

    assert executed == 0
    record_trade.assert_not_called()


def test_run_for_account_returns_zero_when_window_closed_initially() -> None:
    executed = trade_execution_service.run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        get_account_fn=lambda *_a, **_k: make_auto_trading_account(),
        utc_now_iso_fn=lambda: "2026-03-14T00:00:00Z",
        rotate_account_if_due_fn=lambda _conn, _name, account, _now: account,
        record_prepared_trade_fn=Mock(),
        is_submission_window_open_fn=lambda _now: False,
    )
    assert executed == 0
