"""Program A Phase 1: a completed backtest persists all-or-nothing.

The run header, executions, and equity snapshots are wrapped in one
``unit_of_work`` (see ``simulation.run_backtest``). A failure at any write
boundary must roll the whole result tree back, so an interrupted run never leaves
a header that looks complete but has no children.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import backtesting.composition as composition
import backtesting.services.simulation as simulation
from tests.support.backtesting import create_backtest_account, make_backtest_config, stub_market_data_provider


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
    trades = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_executions").fetchone()["n"])
    snaps = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_equity_snapshots").fetchone()["n"])
    return runs, trades, snaps


class TestAtomicBacktestPersistence:
    def test_successful_run_persists_run_with_children(self, conn, bt_market_data) -> None:
        # Establishes that the stub data exercises every write boundary the
        # failure-injection tests target: a header, at least one execution, and
        # multiple snapshots.
        create_backtest_account(conn, "acct_atomic_ok")
        bt_market_data(["AAPL"])

        result = composition.run_backtest(
            conn, make_backtest_config("acct_atomic_ok"), provider=stub_market_data_provider()
        )

        runs, trades, snaps = _research_row_counts(conn)
        assert runs == 1
        assert trades >= 1
        assert snaps > 1
        assert result.run_id is not None

    def test_metrics_only_run_writes_nothing(self, conn, bt_market_data) -> None:
        # The walk-forward optimizer evaluates every grid candidate this way. If a
        # training trial persisted, the search would file its own attempts as
        # backtest evidence and pollute what promotion later reads.
        create_backtest_account(conn, "acct_metrics_only")
        bt_market_data(["AAPL"])

        result = composition.run_backtest_metrics_only(
            conn, make_backtest_config("acct_metrics_only"), provider=stub_market_data_provider()
        )

        assert _research_row_counts(conn) == (0, 0, 0)
        assert result.run_id == 0
        assert result.ending_equity > 0

    def test_failure_at_header_leaves_tables_empty(self, conn, bt_market_data, monkeypatch) -> None:
        create_backtest_account(conn, "acct_atomic_header")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            simulation,
            "insert_run",
            _fail_on_nth_call(simulation.insert_run, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            composition.run_backtest(
                conn, make_backtest_config("acct_atomic_header"), provider=stub_market_data_provider()
            )

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_at_first_snapshot_rolls_back_header(self, conn, bt_market_data, monkeypatch) -> None:
        # The header INSERT has already executed (uncommitted) when the first
        # snapshot fails; the header must not survive.
        create_backtest_account(conn, "acct_atomic_snap")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            simulation,
            "insert_snapshot",
            _fail_on_nth_call(simulation.insert_snapshot, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            composition.run_backtest(
                conn, make_backtest_config("acct_atomic_snap"), provider=stub_market_data_provider()
            )

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_at_first_trade_rolls_back_run(self, conn, bt_market_data, monkeypatch) -> None:
        # Header and first snapshot have executed (uncommitted) before the first
        # execution write fails; nothing may persist.
        create_backtest_account(conn, "acct_atomic_trade")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            simulation,
            "insert_trade",
            _fail_on_nth_call(simulation.insert_trade, nth=1),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            composition.run_backtest(
                conn, make_backtest_config("acct_atomic_trade"), provider=stub_market_data_provider()
            )

        assert _research_row_counts(conn) == (0, 0, 0)

    def test_failure_deep_in_loop_rolls_back_everything(self, conn, bt_market_data, monkeypatch) -> None:
        # A late failure, after many executions and snapshots have accumulated in
        # the open transaction, still leaves no partial tree.
        create_backtest_account(conn, "acct_atomic_late")
        bt_market_data(["AAPL"])
        monkeypatch.setattr(
            simulation,
            "insert_snapshot",
            _fail_on_nth_call(simulation.insert_snapshot, nth=5),
        )

        with pytest.raises(RuntimeError, match="injected backtest write failure"):
            composition.run_backtest(
                conn, make_backtest_config("acct_atomic_late"), provider=stub_market_data_provider()
            )

        assert _research_row_counts(conn) == (0, 0, 0)
