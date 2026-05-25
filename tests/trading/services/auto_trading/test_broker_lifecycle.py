from trading.interfaces.runtime.jobs.run_auto_trades import run_for_account
import trading.services.auto_trading.execution as execution_service
import trading.services.auto_trading.runtime as runtime_service
from tests.trading.services.auto_trading.factories import (
    FakeBroker,
    RuntimeScenario,
    make_account_state,
    make_auto_trading_account,
)


def test_multi_trade_run_creates_one_broker_and_disconnects_once(monkeypatch) -> None:
    broker = FakeBroker()
    scenario = RuntimeScenario(
        account=make_auto_trading_account(id=99),
        state=make_account_state(cash=5000.0),
        prepared_selection=[
            ("buy", "AAPL", 1, 100.0, None, None),
            ("buy", "AAPL", 1, 100.0, None, None),
            ("buy", "AAPL", 1, 100.0, None, None),
        ],
        now_values=["2026-03-14T00:00:00Z"] * 7,
        broker=broker,
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 3)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=3,
        max_trades=3,
        fee=0.0,
    )

    assert executed == 3
    runtime_service.get_broker_for_account.assert_called_once()
    broker.disconnect.assert_called_once()
    assert scenario.trade_recorder.call_count == 3


def test_broker_disconnects_once_even_when_no_trades_execute(monkeypatch) -> None:
    broker = FakeBroker()
    scenario = RuntimeScenario(
        account=make_auto_trading_account(id=55),
        state=make_account_state(cash=5000.0),
        prepared_selection=None,
        now_values=["2026-03-14T00:00:00Z"] * 3,
        broker=broker,
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 2)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=2,
        max_trades=2,
        fee=0.0,
    )

    assert executed == 0
    runtime_service.get_broker_for_account.assert_called_once()
    broker.disconnect.assert_called_once()


def test_standalone_record_runtime_trade_creates_and_disconnects_own_broker(monkeypatch) -> None:
    broker = FakeBroker()
    account = make_auto_trading_account(id=77)

    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _acct: broker)
    monkeypatch.setattr(runtime_service, "insert_broker_order", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime_service, "insert_order_fill", lambda *_a, **_k: None)
    record_trade_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        runtime_service,
        "record_trade",
        lambda _conn, **kwargs: record_trade_calls.append(kwargs),
    )

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
    )

    assert len(record_trade_calls) == 1
    broker.disconnect.assert_called_once()
