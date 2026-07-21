"""Program A Phase 1: a completed backtest persists all-or-nothing.

The run header, executions, and equity snapshots are wrapped in one
``unit_of_work`` (see ``execution_service.run_backtest``). A failure at any write
boundary must roll the whole result tree back, so an interrupted run never leaves
a header that looks complete but has no children.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import trading.backtesting.backtest as backtest_module
from tests.support.backtesting import create_backtest_account, make_backtest_config


def _fail_on_nth_call(real_fn: Callable[..., object], *, nth: int) -> Callable[..., object]:
    """Wrap ``real_fn`` so its nth invocation raises after earlier calls ran normally."""
    state = {"calls": 0}

    def wrapper(*args: object, **kwargs: object) -> object:
        state["calls"] += 1
        if state["calls"] == nth:
            raise RuntimeError("injected backtest write failure")
        return real_fn(*args, **kwargs)

    return wrapper


def _research_row_counts(conn) -> tuple[int, int, int]:
    runs = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_runs").fetchone()["n"])
    trades = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_trades").fetchone()["n"])
    snaps = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_equity_snapshots").fetchone()["n"])
    return runs, trades, snaps


class TestAtomicBacktestPersistence:
    def test_successful_run_persists_run_with_children(self, conn, bt_market_data) -> None:
        # Establishes that the stub data exercises every write boundary the
        # failure-injection tests target: a header, at least one execution, and
        # multiple snapshots.
        create_backtest_account(conn, "acct_atomic_ok")
        bt_market_data(["AAPL"])

        result = backtest_module.run_backtest(conn, make_backtest_config("acct_atomic_ok"))

        runs, trades, snaps = _research_row_counts(conn)
        assert runs == 1
        assert trades >= 1
        assert snaps > 1
        assert result.run_id is not None

    def test_failure_at_header_leaves_tables_empty(self, conn, bt_market_data, monkeypatch) -> None:
        create_backtest_account(conn, "acct_atomic_header")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "insert_backtest_run",
            _fail_on_nth_call(backtest_module.insert_backtest_run, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_atomic_header"))

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_at_first_snapshot_rolls_back_header(self, conn, bt_market_data, monkeypatch) -> None:
        # The header INSERT has already executed (uncommitted) when the first
        # snapshot fails; the header must not survive.
        create_backtest_account(conn, "acct_atomic_snap")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "insert_backtest_snapshot",
            _fail_on_nth_call(backtest_module.insert_backtest_snapshot, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_atomic_snap"))

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_at_first_trade_rolls_back_run(self, conn, bt_market_data, monkeypatch) -> None:
        # Header and first snapshot have executed (uncommitted) before the first
        # execution write fails; nothing may persist.
        create_backtest_account(conn, "acct_atomic_trade")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "insert_backtest_trade",
            _fail_on_nth_call(backtest_module.insert_backtest_trade, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_atomic_trade"))

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_deep_in_loop_rolls_back_everything(self, conn, bt_market_data, monkeypatch) -> None:
        # A late failure, after many executions and snapshots have accumulated in
        # the open transaction, still leaves no partial tree.
        create_backtest_account(conn, "acct_atomic_late")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "insert_backtest_snapshot",
            _fail_on_nth_call(backtest_module.insert_backtest_snapshot, nth=5),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_atomic_late"))

        assert _research_row_counts(conn) == (0, 0, 0)
