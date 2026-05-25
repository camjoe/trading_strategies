from trading.interfaces.runtime.jobs.run_auto_trades import run_for_account
import trading.services.auto_trading.execution as execution_service
import trading.services.auto_trading.runtime as runtime_service
from tests.trading.services.auto_trading.factories import (
    RuntimeScenario,
    make_account_state,
    make_auto_trading_account,
)


def test_run_for_account_uses_rotated_active_strategy(monkeypatch) -> None:
    initial_account = make_auto_trading_account(
        id=11,
        strategy="trend",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )
    rotated_account = make_auto_trading_account(
        id=11,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )
    scenario = RuntimeScenario(
        account=initial_account,
        rotated_account=rotated_account,
        state=make_account_state(),
        prepared_selection=("buy", "AAPL", 1, 100.0, None, None),
        now_values=["2026-03-17T00:00:00Z"] * 3,
    )
    scenario.install(monkeypatch, runtime_service)
    monkeypatch.setattr(execution_service.random, "randint", lambda _a, _b: 1)

    executed = run_for_account(
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
    args, _kwargs = scenario.trade_recorder.call_args
    assert args[6] == "mean_reversion"
