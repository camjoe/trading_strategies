from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import trading.services.execution.selection.selection as trade_execution_service
from tests.src.trading.services.auto_trading.factories import make_option_settings
from tests.support.backtesting import bar_frame
from trading.domain.strategies.contracts import StrategySpec
from trading.domain.strategies.registry import STRATEGY_REGISTRY


def _first_sellable(
    *,
    sell_candidates: list[str],
    forced_sells: list[str],
    prices: dict[str, float],
    positions: dict[str, float],
) -> tuple[str, int, float] | None:
    """The first trade the live sell walk would take, or None if it takes none."""
    return next(
        trade_execution_service.iter_sellable_trades(sell_candidates, forced_sells, prices, positions),
        None,
    )


def test_prepare_buy_trade_equity() -> None:
    state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})
    choose_buy_qty = Mock(return_value=2)
    with patch.object(trade_execution_service, "choose_buy_qty", choose_buy_qty):
        result = trade_execution_service.prepare_buy_trades(
            option_settings=make_option_settings(),
            instrument_mode="equity",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=state,
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert result == [("buy", "AAPL", 2, 100.0, None, None)]
    choose_buy_qty.assert_called_once()


def test_prepare_buy_trade_leaps() -> None:
    state = SimpleNamespace(cash=2000.0, positions={}, avg_cost={})
    option_settings = make_option_settings(max_contracts_per_trade=2)
    with (
        patch.object(
            trade_execution_service,
            "option_candidate_allowed",
            Mock(return_value=(True, 0.4, 30.0)),
        ),
        patch.object(
            trade_execution_service,
            "estimate_option_premium",
            Mock(return_value=120.0),
        ),
        patch.object(
            trade_execution_service,
            "choose_buy_qty",
            Mock(return_value=4),
        ),
    ):
        result = trade_execution_service.prepare_buy_trades(
            option_settings=option_settings,
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={"AAPL": 30.0},
            state=state,
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert result == [("buy", "AAPL", 2, 120.0, 0.4, 30.0)]


def test_prepare_buy_trade_leaps_skips_disallowed_candidate_and_uses_next() -> None:
    state = SimpleNamespace(cash=2000.0, positions={}, avg_cost={})

    def _fake_allowed(_account, ticker, _iv):
        if ticker == "MSFT":
            return True, 0.4, 25.0
        return False, 0.4, 25.0

    with (
        patch.object(trade_execution_service, "option_candidate_allowed", _fake_allowed),
        patch.object(
            trade_execution_service,
            "estimate_option_premium",
            Mock(return_value=100.0),
        ),
        patch.object(trade_execution_service, "choose_buy_qty", Mock(return_value=1)),
    ):
        result = trade_execution_service.prepare_buy_trades(
            option_settings=make_option_settings(),
            instrument_mode="leaps",
            buy_candidates=["AAPL", "MSFT"],
            prices={"AAPL": 100.0, "MSFT": 200.0},
            iv_rank_proxy={"AAPL": 25.0, "MSFT": 25.0},
            state=state,
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert [sel[1] for sel in result] == ["MSFT"]


def test_sellable_trade_closes_the_whole_position() -> None:
    """A sell exits the position outright."""
    result = _first_sellable(
        sell_candidates=[],
        forced_sells=["AAPL"],
        prices={"AAPL": 150.0},
        positions={"AAPL": 5.0},
    )
    assert result == ("AAPL", 5, 150.0)


def test_sellable_trades_prefer_a_risk_breach_over_a_signalled_exit() -> None:
    result = _first_sellable(
        sell_candidates=["MSFT"],
        forced_sells=["AAPL"],
        prices={"AAPL": 150.0, "MSFT": 200.0},
        positions={"AAPL": 5.0, "MSFT": 3.0},
    )
    assert result == ("AAPL", 5, 150.0)


def test_sellable_trades_do_not_sell_a_duplicated_ticker_twice() -> None:
    """A ticker listed twice yields once, because the walk sees the caller's close.

    Consuming the walk without closing each position (collecting it up front, say)
    would sell the same holding twice.
    """
    positions = {"AAPL": 5.0}
    taken = []
    for ticker, qty, price in trade_execution_service.iter_sellable_trades(
        [], ["AAPL", "AAPL"], {"AAPL": 150.0}, positions
    ):
        taken.append((ticker, qty, price))
        positions.pop(ticker, None)

    assert taken == [("AAPL", 5, 150.0)]


def test_prepare_buy_trades_returns_empty_when_no_candidates() -> None:
    result = trade_execution_service.prepare_buy_trades(
        option_settings=make_option_settings(),
        instrument_mode="leaps",
        buy_candidates=[],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0, positions={}, avg_cost={}),
        fee=0.0,
        max_buys=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert result == []


def test_sellable_trades_skip_an_invalid_price() -> None:
    result = _first_sellable(
        sell_candidates=["AAPL"],
        forced_sells=[],
        prices={"AAPL": 0.0},
        positions={"AAPL": 3.0},
    )
    assert result is None


def test_sellable_trades_skip_a_sub_share_position() -> None:
    result = _first_sellable(
        sell_candidates=["AAPL"],
        forced_sells=[],
        prices={"AAPL": 100.0},
        positions={"AAPL": 0.4},
    )
    assert result is None


def test_prepare_buy_trades_returns_empty_when_equity_price_missing() -> None:
    result = trade_execution_service.prepare_buy_trades(
        option_settings=make_option_settings(),
        instrument_mode="equity",
        buy_candidates=["AAPL"],
        prices={},
        iv_rank_proxy={},
        state=SimpleNamespace(cash=1000.0, positions={}, avg_cost={}),
        fee=0.0,
        max_buys=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert result == []


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
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0}, cash=0.0)
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
    with patch.object(trade_execution_service, "choose_buy_qty", Mock(return_value=0)):
        result = trade_execution_service.prepare_buy_trades(
            option_settings=make_option_settings(),
            instrument_mode="equity",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0, positions={}, avg_cost={}),
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert result == []


def test_prepare_buy_trade_leaps_returns_none_for_invalid_option_price_and_qty_limits() -> None:
    with (
        patch.object(
            trade_execution_service,
            "option_candidate_allowed",
            Mock(return_value=(True, 0.4, 20.0)),
        ),
        patch.object(trade_execution_service, "estimate_option_premium", Mock(return_value=50.0)),
        patch.object(trade_execution_service, "choose_buy_qty", Mock(return_value=3)),
        patch.object(trade_execution_service, "apply_leaps_buy_qty_limits", Mock(return_value=0)),
    ):
        invalid_price_result = trade_execution_service.prepare_buy_trades(
            option_settings=make_option_settings(),
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0, positions={}, avg_cost={}),
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
        limited_qty_result = trade_execution_service.prepare_buy_trades(
            option_settings=make_option_settings(),
            instrument_mode="leaps",
            buy_candidates=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            state=SimpleNamespace(cash=1000.0, positions={}, avg_cost={}),
            fee=0.0,
            max_buys=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert invalid_price_result == []
    assert limited_qty_result == []


def _rising_history(length: int = 40) -> "trade_execution_service.pd.DataFrame":
    return bar_frame(trade_execution_service.pd.Series([float(i) for i in range(1, length + 1)]))


def _sell_history() -> "trade_execution_service.pd.DataFrame":
    return bar_frame(trade_execution_service.pd.Series([100.0] * 39 + [90.0]))


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
        {"EMPTY": bar_frame(trade_execution_service.pd.Series(dtype=float))},
        positions={},
    )
    assert buys == []
    assert sells == []


def test_prepare_trade_selection_uses_forced_sell_path() -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0}, cash=0.0)
    option_settings = make_option_settings()

    selection = trade_execution_service.prepare_book_trades(
        option_settings=option_settings,
        active_strategy="trend",
        params={"fast_window": 10, "slow_window": 20},
        state=state,
        forced_sells=["AAPL"],
        universe=["AAPL"],
        prices={"AAPL": 95.0},
        histories={},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=1,
        trade_size_pct=None,
        max_position_pct=None,
    )

    assert selection == [("sell", "AAPL", 2, 95.0, None, None)]


def test_prepare_trade_selection_stops_selling_at_the_trade_budget() -> None:
    state = SimpleNamespace(
        positions={"AAA": 5.0, "BBB": 5.0, "CCC": 5.0},
        avg_cost={"AAA": 100.0, "BBB": 100.0, "CCC": 100.0},
        cash=0.0,
    )

    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy=None,
        params=None,
        state=state,
        forced_sells=["AAA", "BBB", "CCC"],
        universe=[],
        prices={"AAA": 10.0, "BBB": 20.0, "CCC": 30.0},
        histories={},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=2,
        trade_size_pct=None,
        max_position_pct=None,
    )

    assert selection == [
        ("sell", "AAA", 5, 10.0, None, None),
        ("sell", "BBB", 5, 20.0, None, None),
    ]


def test_prepare_trade_selection_funds_a_buy_from_the_same_runs_sell() -> None:
    """The docstring's promise: sells go first so their proceeds fund the run's buys."""
    state = SimpleNamespace(positions={"DOWN": 10.0}, avg_cost={"DOWN": 100.0}, cash=0.0)

    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy="trend",
        params={"fast_window": 10, "slow_window": 20},
        state=state,
        forced_sells=[],
        universe=["UP", "DOWN"],
        prices={"UP": 10.0, "DOWN": 100.0},
        histories={"UP": _rising_history(), "DOWN": _sell_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=2,
        trade_size_pct=None,
        max_position_pct=None,
    )

    sides = [(side, ticker) for side, ticker, *_rest in selection]
    # The book opens with no cash, so the buy exists only because the sell ran first.
    assert sides == [("sell", "DOWN"), ("buy", "UP")]
    assert selection[1][2] >= 1


def test_prepare_trade_selection_hands_buys_the_post_sell_book(monkeypatch) -> None:
    """Cash, positions and avg_cost handed to the buy pass reflect the sells above it.

    Asserted at the handoff because the working book is internal to
    ``prepare_book_trades`` — the returned selections show what was traded, not
    the balances the buy sizing actually saw.
    """
    seen: dict[str, object] = {}

    def _capture(*args, **_kwargs):
        buy_state = args[5]
        seen["cash"] = buy_state.cash
        seen["positions"] = dict(buy_state.positions)
        seen["avg_cost"] = dict(buy_state.avg_cost)
        return []

    monkeypatch.setattr(trade_execution_service, "prepare_buy_trades", _capture)
    state = SimpleNamespace(
        positions={"AAA": 4.0, "KEEP": 2.0},
        avg_cost={"AAA": 90.0, "KEEP": 50.0},
        cash=25.0,
    )

    trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy=None,
        params=None,
        state=state,
        forced_sells=["AAA"],
        universe=[],
        prices={"AAA": 10.0},
        histories={},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=3.0,
        max_trades=2,
        trade_size_pct=None,
        max_position_pct=None,
    )

    # 25 opening cash + (4 * 10) proceeds - 3 fee.
    assert seen["cash"] == pytest.approx(62.0)
    assert seen["positions"] == {"KEEP": 2.0}
    assert seen["avg_cost"] == {"KEEP": 50.0}


def test_prepare_trade_selection_returns_none_when_nothing_signals() -> None:
    # Flat history → hold for the trend strategy; no forced sell → no trade at all.
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy="trend",
        params={"fast_window": 10, "slow_window": 20},
        state=state,
        forced_sells=[],
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        histories={"AAPL": bar_frame(trade_execution_service.pd.Series([100.0] * 40))},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert selection == []


def test_prepare_trade_selection_buys_on_buy_signal() -> None:
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy="trend",
        params={"fast_window": 10, "slow_window": 20},
        state=state,
        forced_sells=[],
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        histories={"AAPL": _rising_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert selection is not None
    assert len(selection) == 1
    side, ticker, qty, trade_price, _delta, _iv = selection[0]
    assert (side, ticker, trade_price) == ("buy", "AAPL", 10.0)
    assert qty >= 1


def test_prepare_trade_selection_sells_on_sell_signal_for_held_ticker() -> None:
    state = SimpleNamespace(positions={"AAPL": 2.0}, avg_cost={"AAPL": 100.0}, cash=0.0)
    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy="trend",
        params={"fast_window": 10, "slow_window": 20},
        state=state,
        forced_sells=[],
        universe=["AAPL"],
        prices={"AAPL": 90.0},
        histories={"AAPL": _sell_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert selection == [("sell", "AAPL", 2, 90.0, None, None)]


def test_prepare_trade_selection_unknown_strategy_holds() -> None:
    state = SimpleNamespace(positions={}, avg_cost={}, cash=1000.0)
    selection = trade_execution_service.prepare_book_trades(
        option_settings=make_option_settings(),
        active_strategy="totally_unknown_xyz",
        params={},
        state=state,
        forced_sells=[],
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        histories={"AAPL": _rising_history()},
        iv_rank_proxy={},
        instrument_mode="equity",
        fee=0.0,
        max_trades=1,
        trade_size_pct=None,
        max_position_pct=None,
    )
    assert selection == []


def test_prepare_trade_selection_returns_buy_selection_with_estimates() -> None:
    with (
        patch.object(
            trade_execution_service,
            "select_signal_trade_candidates",
            Mock(return_value=(["AAPL"], [])),
        ),
        patch.object(
            trade_execution_service,
            "prepare_buy_trades",
            Mock(return_value=[("buy", "AAPL", 2, 100.0, 0.35, 22.0)]),
        ),
    ):
        selection = trade_execution_service.prepare_book_trades(
            option_settings=make_option_settings(),
            active_strategy="trend",
            params={"fast_window": 10, "slow_window": 20},
            state=SimpleNamespace(positions={}, avg_cost={}, cash=1000.0),
            forced_sells=[],
            universe=["AAPL"],
            prices={"AAPL": 100.0},
            histories={"AAPL": _rising_history()},
            iv_rank_proxy={},
            instrument_mode="equity",
            fee=0.0,
            max_trades=1,
            trade_size_pct=None,
            max_position_pct=None,
        )
    assert selection == [("buy", "AAPL", 2, 100.0, 0.35, 22.0)]


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


def test_build_feature_history_fn_returns_none_for_unknown_strategies() -> None:
    fetchers = SimpleNamespace(fetch_policy=Mock(), fetch_news=None, fetch_social=None)

    assert trade_execution_service.build_feature_history_fn(fetchers)("unknown_strategy_xyz", "AAPL") is None
    assert trade_execution_service.build_feature_history_fn(None)("trend", "AAPL") is None


class TestAlternativeFeatureSeam:
    """The live half of the external-feature seam, kept exercised while parked.

    No alternative-style strategy is registered right now — they were retired so
    the price-only behaviours could be confirmed first, and are expected back
    around 2026-09. That leaves every real call to ``build_feature_history_fn``
    returning ``None`` at the style guard, which is why the tests that used to
    cover this went quiet: they named retired strategies, so they stopped
    reaching the code they were written for and passed for the wrong reason.

    These register a synthetic alternative strategy instead, so the wiring stays
    checked. They are also the worked example of what a real strategy must
    declare: a ``StrategySpec`` with ``strategy_style="alternative"``, and an
    entry in ``_ALTERNATIVE_FEATURE_FETCHER_ATTRS`` naming its fetcher.
    """

    STRATEGY_ID = "synthetic_alt"

    @pytest.fixture
    def registered(self, monkeypatch):
        spec = StrategySpec(
            strategy_id=self.STRATEGY_ID,
            signal_fn=lambda _view, _params, _features=None: "hold",
            default_params={},
            strategy_style="alternative",
            required_features=("synthetic_score",),
        )
        monkeypatch.setitem(STRATEGY_REGISTRY, self.STRATEGY_ID, spec)
        monkeypatch.setitem(
            trade_execution_service._ALTERNATIVE_FEATURE_FETCHER_ATTRS, self.STRATEGY_ID, "fetch_policy"
        )
        return spec

    def test_features_reach_the_signal(self, registered) -> None:
        fetchers = SimpleNamespace(
            fetch_policy=Mock(return_value=_StubBundle({"synthetic_score": 0.75})),
            fetch_news=None,
            fetch_social=None,
        )

        row = trade_execution_service.build_feature_history_fn(fetchers)(self.STRATEGY_ID, "AAPL")

        assert row is not None
        assert row["synthetic_score"].iloc[0] == 0.75
        fetchers.fetch_policy.assert_called_once_with("AAPL")

    def test_a_fetcher_that_raises_is_swallowed(self, registered) -> None:
        # The path the retired-strategy tests stopped reaching: a live provider
        # failing must hold the signal, not take the run down.
        fetchers = SimpleNamespace(
            fetch_policy=Mock(side_effect=RuntimeError("boom")), fetch_news=None, fetch_social=None
        )

        assert trade_execution_service.build_feature_history_fn(fetchers)(self.STRATEGY_ID, "AAPL") is None

    def test_an_unavailable_bundle_is_none(self, registered) -> None:
        fetchers = SimpleNamespace(
            fetch_policy=Mock(return_value=_StubBundle(None)), fetch_news=None, fetch_social=None
        )

        assert trade_execution_service.build_feature_history_fn(fetchers)(self.STRATEGY_ID, "AAPL") is None

    def test_a_strategy_with_no_registered_fetcher_is_none(self, monkeypatch) -> None:
        """Declaring the style is not enough — the fetcher entry is the other half."""
        monkeypatch.setitem(
            STRATEGY_REGISTRY,
            self.STRATEGY_ID,
            StrategySpec(
                strategy_id=self.STRATEGY_ID,
                signal_fn=lambda _view, _params, _features=None: "hold",
                default_params={},
                strategy_style="alternative",
            ),
        )
        fetchers = SimpleNamespace(fetch_policy=Mock(), fetch_news=None, fetch_social=None)

        assert trade_execution_service.build_feature_history_fn(fetchers)(self.STRATEGY_ID, "AAPL") is None
        fetchers.fetch_policy.assert_not_called()
