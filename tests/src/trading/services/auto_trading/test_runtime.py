import json
from unittest.mock import Mock

from common.time import utc_now_iso
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.models.orders.broker_order import BrokerOrder, OrderFill, OrderStatus
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import run_for_account
import trading.services.auto_trading.execution as execution_service
import trading.services.auto_trading.runtime as runtime_service
from trading.services.operational_settings import set_runtime_throttle_settings
from tests.src.trading.services.auto_trading.factories import (
    MARKET_CLOSED_TIME_ISO,
    MARKET_OPEN_TIME_ISO,
    RuntimeScenario,
    make_account_state,
    make_feature_fetchers,
    make_auto_trading_account,
)


def test_run_for_account_skips_when_market_closed(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(id=42),
        state=make_account_state(),
        now_values=[MARKET_CLOSED_TIME_ISO],
        window_open_fn=lambda _now: False,
    )
    scenario.install(monkeypatch, runtime_service)
    broker_factory = Mock()

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 0
    broker_factory.assert_not_called()


def test_run_for_account_executes_buy_and_records_trade(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(learning_enabled=1, id=42),
        state=make_account_state(),
        prepared_selection=("buy", "AAPL", 2, 101.0, None, None),
        now_values=[MARKET_OPEN_TIME_ISO, MARKET_OPEN_TIME_ISO, MARKET_OPEN_TIME_ISO],
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 1)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 1
    args, kwargs = scenario.trade_recorder.call_args
    assert args[8][0] == "buy"
    assert args[8][1] == "AAPL"
    assert kwargs["_injected_broker"] is scenario.broker
    scenario.broker.disconnect.assert_called_once()


def test_run_for_account_forced_sell_passes_risk_selection(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(
            learning_enabled=0,
            id=7,
            risk_policy="fixed_stop",
            stop_loss_pct=5.0,
        ),
        state=make_account_state(
            positions={"AAPL": 3.0},
            avg_cost={"AAPL": 100.0},
        ),
        prepared_selection=("sell", "AAPL", 1, 95.0, None, None),
        now_values=[MARKET_OPEN_TIME_ISO, MARKET_OPEN_TIME_ISO, MARKET_OPEN_TIME_ISO],
        forced_sell_ticker="AAPL",
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 1)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 95.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 1
    execution_service.auto_trader_policy.choose_sell_ticker_by_risk.assert_called_once()
    args, _kwargs = scenario.trade_recorder.call_args
    assert args[9] == "AAPL"
    assert args[8][0] == "sell"


def test_run_for_account_skips_iteration_when_trade_not_preparable(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(learning_enabled=1, id=11),
        state=make_account_state(),
        prepared_selection=None,
        now_values=[MARKET_OPEN_TIME_ISO, MARKET_OPEN_TIME_ISO],
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 1)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 0
    scenario.trade_recorder.assert_not_called()


def test_run_for_account_stops_cleanly_when_global_runtime_day_cap_is_hit(monkeypatch, conn) -> None:
    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=1,
        runtime_max_trades_per_minute=None,
        updated_at=utc_now_iso(),
    )
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (11, "AAPL", "buy", 1.0, 100.0, 0.0, "2026-03-14T00:00:00Z", "existing"),
    )
    conn.commit()

    scenario = RuntimeScenario(
        account=make_auto_trading_account(learning_enabled=1, id=11),
        state=make_account_state(),
        prepared_selection=("buy", "AAPL", 1, 101.0, None, None),
        now_values=["2026-03-14T00:00:30Z"] * 3,
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 2)

    executed = run_for_account(
        conn=conn,
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=2,
        max_trades=2,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 0
    scenario.trade_recorder.assert_not_called()


def test_run_for_account_breaks_only_on_runtime_throttle_exception(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(learning_enabled=1, id=42),
        state=make_account_state(),
        prepared_selection=("buy", "AAPL", 2, 101.0, None, None),
        now_values=["2026-03-14T00:00:00Z"] * 3,
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 1)
    monkeypatch.setattr(
        execution_service,
        "enforce_runtime_trade_throttles",
        Mock(side_effect=RuntimeTradeThrottleExceededError("cap hit")),
    )

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 0
    scenario.trade_recorder.assert_not_called()


def test_run_for_account_routes_to_sleeve_mode_without_broker(monkeypatch) -> None:
    scenario = RuntimeScenario(
        account=make_auto_trading_account(learning_enabled=1, id=42),
        state=make_account_state(),
        now_values=[MARKET_OPEN_TIME_ISO],
    )
    scenario.install(monkeypatch, runtime_service)
    sleeve_runner = Mock(return_value=3)
    monkeypatch.setattr(runtime_service, "_run_sleeve_mode_for_account", sleeve_runner)
    broker_factory = Mock()

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=3,
        fee=0.0,
        execution_mode="sleeve",
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 3
    broker_factory.assert_not_called()
    scenario.trade_recorder.assert_not_called()
    assert sleeve_runner.call_count == 1


def test_run_for_account_uses_account_specific_universe_for_account_mode(monkeypatch) -> None:
    account = make_auto_trading_account(id=42, trade_universes=json.dumps(["tech", "growth"]))
    scenario = RuntimeScenario(
        account=account,
        state=make_account_state(),
        now_values=[MARKET_OPEN_TIME_ISO],
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(runtime_service, "_rotate_runtime_account", Mock(return_value=account))
    monkeypatch.setattr(runtime_service, "resolve_named_universes", Mock(return_value=["AAPL", "MSFT"]))
    impl = Mock(return_value=0)
    monkeypatch.setattr(runtime_service, "run_for_account_impl", impl)

    run_for_account(
        conn=object(),
        account_name="acct",
        universe=["SPY"],
        prices={"AAPL": 101.0, "MSFT": 200.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    runtime_service.resolve_named_universes.assert_called_once_with(["tech", "growth"])
    args = impl.call_args.args
    assert args[2] == ["AAPL", "MSFT"]
    scenario.broker.disconnect.assert_called_once()


def test_run_for_account_falls_back_to_global_universe_when_account_universe_is_empty_list(monkeypatch) -> None:
    account = make_auto_trading_account(id=42, trade_universes="[]")
    scenario = RuntimeScenario(
        account=account,
        state=make_account_state(),
        now_values=[MARKET_OPEN_TIME_ISO],
    )
    scenario.install(monkeypatch, runtime_service)
    impl = Mock(return_value=0)
    monkeypatch.setattr(runtime_service, "run_for_account_impl", impl)

    run_for_account(
        conn=object(),
        account_name="acct",
        universe=["SPY"],
        prices={"SPY": 500.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _: scenario.broker,
        feature_fetchers=make_feature_fetchers(),
    )

    args = impl.call_args.args
    assert args[2] == ["SPY"]
    scenario.broker.disconnect.assert_called_once()


def test_reconcile_open_ib_orders_delegates_to_broker_reconciliation(monkeypatch) -> None:
    reconcile = Mock(return_value=3)
    monkeypatch.setattr(runtime_service, "reconcile_open_broker_orders", reconcile)

    count = runtime_service.reconcile_open_ib_orders(
        conn=object(),
        account_name="acct",
        account=make_auto_trading_account(id=1),
        fee=1.5,
        broker_factory=Mock(),
    )

    assert count == 3
    reconcile.assert_called_once()


def test_runtime_wrapper_delegates(monkeypatch) -> None:
    rotated = Mock(return_value="rotated")
    refreshed = Mock(return_value="state")
    resolved_exec = Mock(return_value="exec-id")
    computed_snapshot = Mock(return_value=(1.0, 2.0, 3.0, 4.0))
    monkeypatch.setattr(runtime_service, "rotate_runtime_account", rotated)
    monkeypatch.setattr(runtime_service, "refresh_account_state_impl", refreshed)
    monkeypatch.setattr(runtime_service, "resolve_reconciliation_exec_id", resolved_exec)
    monkeypatch.setattr(runtime_service, "compute_current_exposure_snapshot", computed_snapshot)

    account = make_auto_trading_account(id=42)
    assert (
        runtime_service._rotate_runtime_account(
            object(),
            "acct",
            account,
            "now",
            feature_fetchers=make_feature_fetchers(),
        )
        == "rotated"
    )
    assert runtime_service._refresh_runtime_account_state(object(), account) == "state"
    assert (
        runtime_service._resolve_reconciliation_exec_id(
            broker_order_id="b1",
            fill=Mock(),
            fill_index=0,
        )
        == "exec-id"
    )
    assert runtime_service._compute_current_exposure_snapshot(object(), account_id=42) == (1.0, 2.0, 3.0, 4.0)


def test_is_runtime_submission_window_open_parses_iso_before_market_hours_check(monkeypatch) -> None:
    parse_iso = Mock(return_value="parsed-dt")
    market_open = Mock(return_value=True)
    monkeypatch.setattr(runtime_service, "parse_utc_iso", parse_iso)
    monkeypatch.setattr(runtime_service, "is_regular_us_equity_market_open", market_open)

    assert runtime_service._is_runtime_submission_window_open("2026-03-14T14:00:00Z") is True
    parse_iso.assert_called_once_with("2026-03-14T14:00:00Z")
    market_open.assert_called_once_with("parsed-dt")


def test_record_runtime_trade_skips_broker_order_inserts_when_broker_id_missing(monkeypatch) -> None:
    account = make_auto_trading_account(id=1)
    broker = Mock()
    broker.place_order.return_value = BrokerOrder(
        account_id=1,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        broker_order_id=None,
        status=OrderStatus.FILLED,
        filled_qty=1.0,
        avg_fill_price=101.0,
    )
    mock_repo = Mock()
    monkeypatch.setattr(runtime_service, "BrokerOrderRepository", lambda conn: mock_repo)
    monkeypatch.setattr(runtime_service, "record_trade", Mock())

    runtime_service._record_runtime_trade(
        object(),
        "acct",
        account,
        False,
        "none",
        "equity",
        "trend",
        0.0,
        ("buy", "AAPL", 1, 100.0, None, None),
        None,
        _injected_broker=broker,
    )

    mock_repo.insert_order.assert_not_called()
    mock_repo.insert_fill.assert_not_called()
    runtime_service.record_trade.assert_called_once()
    broker.disconnect.assert_not_called()


def test_record_runtime_trade_does_not_record_when_order_not_filled(monkeypatch) -> None:
    account = make_auto_trading_account(id=1)
    broker = Mock()
    broker.place_order.return_value = BrokerOrder(
        account_id=1,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        broker_order_id="b-1",
        status=OrderStatus.SUBMITTED,
        filled_qty=0.0,
        avg_fill_price=None,
    )
    mock_repo = Mock()
    monkeypatch.setattr(runtime_service, "BrokerOrderRepository", lambda conn: mock_repo)
    monkeypatch.setattr(runtime_service, "record_trade", Mock())

    runtime_service._record_runtime_trade(
        object(),
        "acct",
        account,
        False,
        "none",
        "equity",
        "trend",
        0.0,
        ("buy", "AAPL", 1, 100.0, None, None),
        None,
        _injected_broker=broker,
    )

    mock_repo.insert_order.assert_called_once()
    runtime_service.record_trade.assert_not_called()


def test_record_runtime_trade_inserts_order_fills_when_present(monkeypatch) -> None:
    account = make_auto_trading_account(id=1)
    broker = Mock()
    broker.place_order.return_value = BrokerOrder(
        account_id=1,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        broker_order_id="b-1",
        status=OrderStatus.FILLED,
        filled_qty=1.0,
        avg_fill_price=101.0,
        fills=[
            OrderFill(
                filled_qty=1.0,
                fill_price=101.0,
                fill_time="2026-03-14T14:00:00Z",
                commission=0.1,
                exec_id="exec-1",
            )
        ],
    )
    mock_repo = Mock()
    monkeypatch.setattr(runtime_service, "BrokerOrderRepository", lambda conn: mock_repo)
    monkeypatch.setattr(runtime_service, "record_trade", Mock())

    runtime_service._record_runtime_trade(
        object(),
        "acct",
        account,
        False,
        "none",
        "equity",
        "trend",
        0.0,
        ("buy", "AAPL", 1, 100.0, None, None),
        None,
        _injected_broker=broker,
    )

    mock_repo.insert_fill.assert_called_once()
