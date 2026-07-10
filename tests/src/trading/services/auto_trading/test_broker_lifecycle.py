from unittest.mock import Mock

from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import run_for_account
from trading.repositories.book_bridge import default_book_id
from trading.services.accounts import get_account
import trading.services.auto_trading.runtime as runtime_service
from tests.src.trading.services.auto_trading.factories import (
    FakeBroker,
    RuntimeScenario,
    make_account_state,
    make_feature_fetchers,
    make_auto_trading_account,
)
from tests.support.repositories import insert_repository_account


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
    broker_factory = Mock(return_value=broker)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=3,
        fee=0.0,
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 3
    broker_factory.assert_called_once()
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
    broker_factory = Mock(return_value=broker)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=2,
        fee=0.0,
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed == 0
    broker_factory.assert_called_once()
    broker.disconnect.assert_called_once()


def test_caller_owns_broker_lifecycle_when_injecting_broker(conn, monkeypatch) -> None:
    broker = FakeBroker()
    account_id = insert_repository_account(conn, name="acct", initial_cash=10_000.0)
    default_book_id(conn, account_id)  # bootstrap the account's default book
    account = get_account(conn, "acct")

    record_trade_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        runtime_service,
        "record_trade",
        lambda _conn, **kwargs: record_trade_calls.append(kwargs),
    )

    runtime_service._record_runtime_trade(
        conn,
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
        _prices={"AAPL": 101.0},
        _snapshot_time="2026-03-14T14:00:00Z",
    )

    # _record_runtime_trade must not disconnect an injected broker — the caller owns it.
    assert len(record_trade_calls) == 1
    broker.disconnect.assert_not_called()
