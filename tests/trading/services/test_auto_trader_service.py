from types import SimpleNamespace

import pandas as pd
import pytest

from common.time import parse_utc_iso
import trading.services.auto_trading as auto_trading_service
import trading.services.auto_trading.rotation as rotation_service
from trading.services.accounts import create_account, get_account
from trading.repositories.rotation import update_account_rotation_state
from trading.domain.rotation import next_rotation_state, parse_rotation_schedule, resolve_active_strategy, resolve_optimality_mode, resolve_rotation_mode
from trading.services.auto_trading import RotationDeps
from tests.support import make_account_record


def _base_account(**overrides):
    values: dict[str, object] = {
        "option_strike_offset_pct": 5.0,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
        "rotation_enabled": 0,
        "rotation_schedule": None,
        "rotation_active_index": 0,
        "rotation_last_at": None,
        "rotation_active_strategy": None,
        "rotation_mode": "time",
        "rotation_optimality_mode": "previous_period_best",
        "rotation_lookback_days": 180,
        "rotation_overlay_mode": "none",
    }
    values.update(overrides)
    return make_account_record(**values)


def _insert_backtest_run(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    end_date: str,
    start_equity: float,
    end_equity: float,
) -> None:
    run_id = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_name,
            run_name,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            notes,
            warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_name,
            f"{strategy_name}-{end_date}",
            "2026-01-01",
            end_date,
            f"{end_date}T00:00:00Z",
            0.0,
            0.0,
            "",
            "",
        ),
    ).lastrowid

    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-01-01T00:00:00Z",
            start_equity,
            0.0,
            start_equity,
            0.0,
            0.0,
            run_id,
            f"{end_date}T00:00:00Z",
            end_equity,
            0.0,
            end_equity,
            0.0,
            0.0,
        ),
    )
    conn.commit()


def test_build_iv_rank_proxy_handles_empty_and_single() -> None:
    def fake_fetch_close_series(ticker: str, period: str):
        assert period == "1y"
        if ticker == "EMPTY":
            return None
        if ticker == "ONE":
            return pd.Series(range(1, 50), dtype=float)
        return None

    assert auto_trading_service.build_iv_rank_proxy(["EMPTY"], fetch_close_series_fn=fake_fetch_close_series) == {}
    assert auto_trading_service.build_iv_rank_proxy(["ONE"], fetch_close_series_fn=fake_fetch_close_series) == {"ONE": 50.0}


def test_validate_trade_count_range_and_account_names() -> None:
    with pytest.raises(ValueError, match="min-trades"):
        auto_trading_service.validate_trade_count_range(0, 1)
    with pytest.raises(ValueError, match="max-trades"):
        auto_trading_service.validate_trade_count_range(2, 1)

    assert auto_trading_service.resolve_account_names("acct1, acct2") == ["acct1", "acct2"]
    with pytest.raises(ValueError, match="No accounts"):
        auto_trading_service.resolve_account_names(" , ")


def test_resolve_market_inputs_and_run_accounts() -> None:
    universe, prices, iv_rank = auto_trading_service.resolve_market_inputs(
        "tickers.txt",
        load_tickers_from_file_fn=lambda _path: ["AAPL"],
        fetch_latest_prices_fn=lambda _universe: {"AAPL": 101.0},
        build_iv_rank_proxy_fn=lambda _universe: {"AAPL": 50.0},
    )
    assert universe == ["AAPL"]
    assert prices == {"AAPL": 101.0}
    assert iv_rank == {"AAPL": 50.0}

    results = auto_trading_service.run_accounts(
        conn=object(),
        account_names=["acct1", "acct2"],
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank,
        min_trades=1,
        max_trades=2,
        fee=0.0,
        run_for_account_fn=lambda **kwargs: 2 if kwargs["account_name"] == "acct1" else 1,
    )
    assert results == [("acct1", 2), ("acct2", 1)]


def test_parse_runtime_as_of_iso_and_safe_return_pct() -> None:
    naive = parse_utc_iso("2026-03-21T12:00:00")
    zulu = parse_utc_iso("2026-03-21T12:00:00Z")
    parsed = parse_utc_iso("2026-03-21T12:00:00+02:00")

    assert naive.isoformat().endswith("+00:00")
    assert zulu.isoformat().endswith("+00:00")
    assert parsed.isoformat().endswith("+00:00")


def test_rotate_runtime_account_if_due_updates_state(monkeypatch) -> None:
    account_before = _base_account(
        id=9,
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )

    class _Conn:
        def __init__(self):
            self.updated = None
            self.committed = False

        def execute(self, _sql, params):
            self.updated = params

        def commit(self):
            self.committed = True

    conn = _Conn()
    account_after = _base_account(
        id=9,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )

    out = auto_trading_service.rotate_runtime_account_if_due(
        conn,
        "acct",
        account_before,
        "2026-03-17T00:00:00Z",
        RotationDeps(
            rotate_account_if_due_impl_fn=rotation_service.rotate_account_if_due,
            is_rotation_due_fn=lambda _row: True,
            resolve_rotation_mode_fn=resolve_rotation_mode,
            select_optimal_strategy_fn=lambda *_args, **_kwargs: None,
            resolve_active_strategy_fn=resolve_active_strategy,
            parse_rotation_schedule_fn=parse_rotation_schedule,
            next_rotation_state_fn=lambda row, as_of: next_rotation_state(row, as_of_iso=as_of),
            update_account_rotation_state_fn=update_account_rotation_state,
            get_account_fn=lambda _conn, _name: account_after,
        ),
    )

    assert conn.committed is True
    assert conn.updated is not None
    assert conn.updated[0] == "mean_reversion"
    assert out["strategy"] == "mean_reversion"


def test_rotate_runtime_account_if_due_optimal_previous_period_best(conn) -> None:
    create_account(conn, "acct_opt_prev", "trend", 10000.0, "SPY")
    account = get_account(conn, "acct_opt_prev")
    assert account is not None

    conn.execute(
        """
        UPDATE accounts
        SET rotation_enabled = 1,
            rotation_interval_days = 7,
            rotation_schedule = ?,
            rotation_active_index = 0,
            rotation_active_strategy = 'trend',
            rotation_last_at = '2026-03-01T00:00:00Z',
            rotation_mode = 'optimal',
            rotation_optimality_mode = 'previous_period_best',
            rotation_lookback_days = 120
        WHERE name = 'acct_opt_prev'
        """,
        ('["trend","mean_reversion"]',),
    )
    conn.commit()

    account = get_account(conn, "acct_opt_prev")
    _insert_backtest_run(conn, account_id=int(account["id"]), strategy_name="trend", end_date="2026-03-08", start_equity=10000.0, end_equity=10600.0)
    _insert_backtest_run(conn, account_id=int(account["id"]), strategy_name="mean_reversion", end_date="2026-03-15", start_equity=10000.0, end_equity=11200.0)

    rotated = auto_trading_service.rotate_runtime_account_if_due(
        conn,
        "acct_opt_prev",
        account,
        "2026-03-20T00:00:00Z",
        RotationDeps(
            rotate_account_if_due_impl_fn=rotation_service.rotate_account_if_due,
            is_rotation_due_fn=lambda row: resolve_rotation_mode(row) == "optimal" and True,
            resolve_rotation_mode_fn=resolve_rotation_mode,
            select_optimal_strategy_fn=lambda inner_conn, inner_account, inner_as_of: auto_trading_service.select_account_rotation_strategy(
                inner_conn,
                inner_account,
                inner_as_of,
                select_optimal_strategy_impl_fn=rotation_service.select_optimal_strategy,
                select_regime_strategy_impl_fn=None,
                parse_rotation_schedule_fn=parse_rotation_schedule,
                parse_as_of_iso_fn=parse_utc_iso,
                fetch_strategy_backtest_returns_fn=__import__("trading.backtesting.services.history_service", fromlist=["fetch_strategy_backtest_returns"]).fetch_strategy_backtest_returns,
                fetch_policy_features_fn=None,
                resolve_rotation_mode_fn=resolve_rotation_mode,
                resolve_active_strategy_fn=resolve_active_strategy,
                resolve_optimality_mode_fn=resolve_optimality_mode,
            ),
            resolve_active_strategy_fn=resolve_active_strategy,
            parse_rotation_schedule_fn=parse_rotation_schedule,
            next_rotation_state_fn=lambda row, as_of: next_rotation_state(row, as_of_iso=as_of),
            update_account_rotation_state_fn=update_account_rotation_state,
            get_account_fn=get_account,
        ),
    )
    assert rotated["strategy"] == "mean_reversion"
    assert rotated["rotation_active_strategy"] == "mean_reversion"


def test_rotate_runtime_account_if_due_noop_when_not_due() -> None:
    account = _base_account(rotation_enabled=1, rotation_interval_days=30, rotation_last_at="2026-03-20T00:00:00Z")
    out = auto_trading_service.rotate_runtime_account_if_due(
        conn=object(),
        account_name="acct",
        account=account,
        now_iso="2026-03-21T00:00:00Z",
        deps=RotationDeps(
            rotate_account_if_due_impl_fn=rotation_service.rotate_account_if_due,
            is_rotation_due_fn=lambda *_args, **_kwargs: False,
            resolve_rotation_mode_fn=resolve_rotation_mode,
            select_optimal_strategy_fn=lambda *_args, **_kwargs: None,
            resolve_active_strategy_fn=resolve_active_strategy,
            parse_rotation_schedule_fn=parse_rotation_schedule,
            next_rotation_state_fn=lambda row, as_of: next_rotation_state(row, as_of_iso=as_of),
            update_account_rotation_state_fn=update_account_rotation_state,
            get_account_fn=get_account,
        ),
    )
    assert out is account


def test_select_account_rotation_strategy_returns_none_when_no_runs(conn) -> None:
    account = _base_account(id=123, rotation_schedule='["trend","mean_reversion"]')
    history_service = __import__("trading.backtesting.services.history_service", fromlist=["fetch_strategy_backtest_returns"])
    assert auto_trading_service.select_account_rotation_strategy(
        conn,
        account,
        "2026-03-21T00:00:00Z",
        select_optimal_strategy_impl_fn=rotation_service.select_optimal_strategy,
        select_regime_strategy_impl_fn=None,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=parse_utc_iso,
        fetch_strategy_backtest_returns_fn=history_service.fetch_strategy_backtest_returns,
        fetch_policy_features_fn=None,
        resolve_rotation_mode_fn=resolve_rotation_mode,
        resolve_active_strategy_fn=resolve_active_strategy,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    ) is None


def test_select_account_rotation_strategy_returns_none_when_schedule_empty(conn) -> None:
    account = _base_account(id=123, rotation_schedule="[]")
    history_service = __import__("trading.backtesting.services.history_service", fromlist=["fetch_strategy_backtest_returns"])
    assert auto_trading_service.select_account_rotation_strategy(
        conn,
        account,
        "2026-03-21T00:00:00Z",
        select_optimal_strategy_impl_fn=rotation_service.select_optimal_strategy,
        select_regime_strategy_impl_fn=None,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=parse_utc_iso,
        fetch_strategy_backtest_returns_fn=history_service.fetch_strategy_backtest_returns,
        fetch_policy_features_fn=None,
        resolve_rotation_mode_fn=resolve_rotation_mode,
        resolve_active_strategy_fn=resolve_active_strategy,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    ) is None


def test_select_account_rotation_strategy_uses_regime_mapping() -> None:
    account = _base_account(
        rotation_mode="regime",
        rotation_schedule='["trend","ma_crossover","mean_reversion"]',
        rotation_active_strategy="ma_crossover",
        rotation_regime_strategy_risk_on="trend",
        rotation_regime_strategy_neutral="ma_crossover",
        rotation_regime_strategy_risk_off="mean_reversion",
    )

    selected = auto_trading_service.select_account_rotation_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-21T00:00:00Z",
        select_optimal_strategy_impl_fn=lambda *_args, **_kwargs: None,
        select_regime_strategy_impl_fn=rotation_service.select_regime_strategy,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=parse_utc_iso,
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=lambda _ticker: SimpleNamespace(
            available=True,
            get=lambda key, default=None: {
                "policy_risk_on_score": 0.40,
                "policy_defensive_tilt": 0.03,
            }.get(key, default),
        ),
        resolve_rotation_mode_fn=resolve_rotation_mode,
        resolve_active_strategy_fn=resolve_active_strategy,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    )

    assert selected == "mean_reversion"


def test_select_account_rotation_strategy_passes_overlay_dependencies() -> None:
    account = _base_account(
        rotation_mode="regime",
        rotation_overlay_mode="news_social",
    )
    calls: dict[str, object] = {}

    selected = auto_trading_service.select_account_rotation_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-21T00:00:00Z",
        select_optimal_strategy_impl_fn=lambda *_args, **_kwargs: None,
        select_regime_strategy_impl_fn=lambda row, **kwargs: calls.update(kwargs) or row["strategy"],
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=parse_utc_iso,
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=lambda _ticker: SimpleNamespace(available=False, get=lambda *_args, **_kwargs: None),
        fetch_news_features_fn=lambda _ticker: SimpleNamespace(available=False, get=lambda *_args, **_kwargs: None),
        fetch_social_features_fn=lambda _ticker: SimpleNamespace(available=False, get=lambda *_args, **_kwargs: None),
        fetch_rotation_overlay_tickers_fn=lambda _conn, _account: ["AAPL"],
        resolve_rotation_mode_fn=resolve_rotation_mode,
        resolve_active_strategy_fn=resolve_active_strategy,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    )

    assert selected == "trend"
    assert calls["fetch_news_features_fn"] is not None
    assert calls["fetch_social_features_fn"] is not None
    assert calls["fetch_rotation_overlay_tickers_fn"] is not None
