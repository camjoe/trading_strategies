from unittest.mock import Mock

from common.time import utc_now_iso
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.interfaces.runtime.jobs.run_auto_trades import run_for_account
import trading.services.auto_trading.execution as execution_service
import trading.services.auto_trading.runtime as runtime_service
from trading.services.runtime_settings import set_runtime_throttle_settings
from tests.support import (
    MARKET_CLOSED_TIME_ISO,
    MARKET_OPEN_TIME_ISO,
    RuntimeScenario,
    make_account_state,
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

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )

    assert executed == 0
    runtime_service.get_broker_for_account.assert_not_called()


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
    )

    assert executed == 0
    scenario.trade_recorder.assert_not_called()
