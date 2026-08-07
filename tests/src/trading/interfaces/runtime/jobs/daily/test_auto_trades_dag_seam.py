"""The orchestration/trading seam: a trading exit code becoming a DAG step status.

Tests either side of this boundary stub the other. These take the code
`run_auto_trades.main()` really returns and drive the real step wiring with it,
so only the subprocess call itself is stubbed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

import infrastructure.database.connection as init_module
import trading.interfaces.runtime.jobs.job_helpers as job_helpers
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_run_auto_trades_args,
    run_auto_trades,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.dag import (
    new_step_results,
    run_dag_step,
    step_result,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.workflow import run_auto_trader_group
from trading.models.execution import AccountRunResult

TRADING_STEP_ID = "05_build_position_targets_by_book"


class FakeConn:
    def close(self) -> None:
        pass


def _exit_code_for(monkeypatch, results: list[AccountRunResult]) -> int:
    """The code `main()` returns when the runtime reports *results*."""
    monkeypatch.setattr(run_auto_trades, "parse_args", lambda: make_run_auto_trades_args(accounts="acct1"))
    monkeypatch.setattr(run_auto_trades, "resolve_run_universe", lambda _conn, _accounts: ["AAPL"])
    monkeypatch.setattr(
        run_auto_trades,
        "resolve_market_inputs",
        lambda _p, **_kwargs: (["AAPL"], {"AAPL": 100.0}, {}, {}),
    )
    monkeypatch.setattr(init_module, "ensure_db", lambda: FakeConn())
    monkeypatch.setattr(run_auto_trades, "run_accounts", Mock(return_value=results))
    return run_auto_trades.main()


def _trading_step_status(monkeypatch, exit_code: int) -> str:
    """Status of DAG step 05 when the auto-trades subprocess exits with *exit_code*."""
    monkeypatch.setattr(job_helpers, "run_command", lambda *_args, **_kwargs: (exit_code, ""))
    step_results = new_step_results()

    def _run_group() -> dict[str, object]:
        run_auto_trader_group(
            Path("run.log"),
            Path("."),
            "Auto Trader",
            ["acct1"],
            max_trades=5,
            fee=0.0,
            seed=None,
        )
        return {}

    try:
        run_dag_step(step_results, step_id=TRADING_STEP_ID, run_fn=_run_group, now_iso=lambda: "2026-08-07T12:00:00Z")
    except RuntimeError:
        pass
    return step_result(step_results, TRADING_STEP_ID).status


def test_broker_anomaly_fails_the_trading_step(monkeypatch) -> None:
    """The one halt that must not read as a clean run: orders may exist in an unknown state."""
    exit_code = _exit_code_for(
        monkeypatch,
        [
            AccountRunResult(
                account_name="acct1",
                submitted_count=1,
                kill_switch_reasons=("broker_api_anomaly",),
            )
        ],
    )

    assert exit_code == 1
    assert _trading_step_status(monkeypatch, exit_code) == "failed"


def test_a_control_halt_leaves_the_trading_step_green(monkeypatch) -> None:
    """A stale-price or reconciliation halt is a control working, not a run failure."""
    exit_code = _exit_code_for(
        monkeypatch,
        [
            AccountRunResult(
                account_name="acct1",
                submitted_count=0,
                kill_switch_reasons=("stale_price_data",),
            )
        ],
    )

    assert exit_code == 0
    assert _trading_step_status(monkeypatch, exit_code) == "ok"


def test_the_step_reports_the_failing_exit_code(monkeypatch) -> None:
    """The operator has to be able to tell which subprocess failed and how."""
    monkeypatch.setattr(job_helpers, "run_command", lambda *_args, **_kwargs: (1, ""))
    step_results = new_step_results()

    with pytest.raises(RuntimeError, match=r"Auto Trader \(exit=1\)"):
        run_dag_step(
            step_results,
            step_id=TRADING_STEP_ID,
            run_fn=lambda: run_auto_trader_group(
                Path("run.log"),
                Path("."),
                "Auto Trader",
                ["acct1"],
                max_trades=5,
                fee=0.0,
                seed=None,
            ),
            now_iso=lambda: "2026-08-07T12:00:00Z",
        )

    assert step_result(step_results, TRADING_STEP_ID).error == "Step failed: Auto Trader (exit=1)"
