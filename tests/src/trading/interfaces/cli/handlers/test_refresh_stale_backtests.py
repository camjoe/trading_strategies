from __future__ import annotations

import types

from tests.src.trading.interfaces.cli.factories import make_backtest_result
from trading.interfaces.cli.handlers.backtesting_handlers import handle_refresh_stale_backtests


def _target(account: str, strategy: str, *, age_days: float | None, reason: str):
    return types.SimpleNamespace(
        account_name=account, account_id=1, strategy_name=strategy, age_days=age_days, reason=reason
    )


def _args(**overrides):
    defaults = {
        "account": None,
        "dry_run": False,
        "limit": None,
        "tickers_file": "tickers.txt",
        "universe_history_dir": None,
        "start": None,
        "end": None,
        "lookback_months": None,
        "slippage_bps": 5.0,
        "fee": 0.0,
        "allow_approximate_leaps": False,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


_TWO_TARGETS = [
    _target("acct1", "meanrev", age_days=6.0, reason="stale"),
    _target("acct1", "breakout", age_days=None, reason="missing"),
]


def test_dry_run_lists_targets_without_running(capsys) -> None:
    ran: list = []
    deps = {
        "find_stale_backtests": lambda _conn, *, account_name: list(_TWO_TARGETS),
        "run_backtest": lambda *_a, **_k: ran.append(1),
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
    }

    handle_refresh_stale_backtests(object(), _args(dry_run=True), _parser(), deps=deps)

    out = capsys.readouterr().out
    assert ran == []
    assert "acct1/meanrev (stale, 6.0d)" in out
    assert "acct1/breakout (missing, missing)" in out


def test_execute_runs_a_backtest_per_target_with_strategy_override(capsys) -> None:
    configs: list = []
    deps = {
        "find_stale_backtests": lambda _conn, *, account_name: list(_TWO_TARGETS),
        "run_backtest": lambda _conn, cfg: (configs.append(cfg), make_backtest_result(run_id=len(configs)))[1],
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
    }

    handle_refresh_stale_backtests(object(), _args(), _parser(), deps=deps)

    assert [c.strategy for c in configs] == ["meanrev", "breakout"]
    assert all(c.account_name == "acct1" for c in configs)
    out = capsys.readouterr().out
    assert "Done: 2 refreshed, 0 failed." in out


def test_limit_caps_the_batch() -> None:
    configs: list = []
    deps = {
        "find_stale_backtests": lambda _conn, *, account_name: list(_TWO_TARGETS),
        "run_backtest": lambda _conn, cfg: (configs.append(cfg), make_backtest_result())[1],
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
    }

    handle_refresh_stale_backtests(object(), _args(limit=1), _parser(), deps=deps)

    assert [c.strategy for c in configs] == ["meanrev"]


def test_failure_on_one_target_does_not_abort_batch(capsys) -> None:
    def _run(_conn, cfg):
        if cfg.strategy == "meanrev":
            raise ValueError("Unknown strategy 'meanrev'")
        return make_backtest_result(run_id=9)

    deps = {
        "find_stale_backtests": lambda _conn, *, account_name: list(_TWO_TARGETS),
        "run_backtest": _run,
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
    }

    handle_refresh_stale_backtests(object(), _args(), _parser(), deps=deps)

    out = capsys.readouterr().out
    assert "Failed acct1/meanrev: Unknown strategy 'meanrev'" in out
    assert "Refreshed acct1/breakout: run_id=9" in out
    assert "Done: 1 refreshed, 1 failed." in out


def test_no_targets_prints_clean_message(capsys) -> None:
    deps = {"find_stale_backtests": lambda _conn, *, account_name: []}

    handle_refresh_stale_backtests(object(), _args(), _parser(), deps=deps)

    assert "No stale or missing backtests found." in capsys.readouterr().out
