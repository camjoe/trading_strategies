import trading.services.auto_trading as auto_trading_service
from trading.services.accounts import create_account, get_account
from trading.repositories.rotation import update_account_rotation_state
from trading.services.auto_trading import RotationDeps
from tests.support import make_auto_trading_account, make_feature_bundle


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


def test_rotate_runtime_account_if_due_updates_state() -> None:
    account_before = make_auto_trading_account(
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
    account_after = make_auto_trading_account(
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
            is_rotation_due_fn=lambda _row: True,
            select_optimal_strategy_fn=lambda *_args, **_kwargs: None,
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
            is_rotation_due_fn=lambda _row: True,
            select_optimal_strategy_fn=lambda inner_conn, inner_account, inner_as_of: auto_trading_service.select_account_rotation_strategy(
                inner_conn,
                inner_account,
                inner_as_of,
                fetch_strategy_backtest_returns_fn=__import__(
                    "trading.backtesting.services.history_service",
                    fromlist=["fetch_strategy_backtest_returns"],
                ).fetch_strategy_backtest_returns,
                fetch_policy_features_fn=None,
            ),
            update_account_rotation_state_fn=update_account_rotation_state,
            get_account_fn=get_account,
        ),
    )

    assert rotated["strategy"] == "mean_reversion"
    assert rotated["rotation_active_strategy"] == "mean_reversion"


def test_rotate_runtime_account_if_due_noop_when_not_due() -> None:
    account = make_auto_trading_account(
        rotation_enabled=1,
        rotation_interval_days=30,
        rotation_last_at="2026-03-20T00:00:00Z",
    )

    out = auto_trading_service.rotate_runtime_account_if_due(
        conn=object(),
        account_name="acct",
        account=account,
        now_iso="2026-03-21T00:00:00Z",
        deps=RotationDeps(
            is_rotation_due_fn=lambda *_args, **_kwargs: False,
            select_optimal_strategy_fn=lambda *_args, **_kwargs: None,
            update_account_rotation_state_fn=update_account_rotation_state,
            get_account_fn=get_account,
        ),
    )

    assert out is account


def test_select_account_rotation_strategy_returns_none_when_no_runs(conn) -> None:
    account = make_auto_trading_account(id=123, rotation_schedule='["trend","mean_reversion"]')

    assert auto_trading_service.select_account_rotation_strategy(
        conn,
        account,
        "2026-03-21T00:00:00Z",
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=None,
    ) is None


def test_select_account_rotation_strategy_returns_none_when_schedule_empty(conn) -> None:
    account = make_auto_trading_account(id=123, rotation_schedule="[]")

    assert auto_trading_service.select_account_rotation_strategy(
        conn,
        account,
        "2026-03-21T00:00:00Z",
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=None,
    ) is None


def test_select_account_rotation_strategy_uses_regime_mapping() -> None:
    account = make_auto_trading_account(
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
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(
            policy_risk_on_score=0.40,
            policy_defensive_tilt=0.03,
        ),
    )

    assert selected == "mean_reversion"


def test_select_account_rotation_strategy_passes_overlay_dependencies() -> None:
    account = make_auto_trading_account(
        rotation_mode="regime",
        rotation_overlay_mode="news_social",
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_strategy="trend",
        rotation_regime_strategy_risk_on="trend",
        rotation_regime_strategy_neutral="trend",
        rotation_regime_strategy_risk_off="mean_reversion",
    )
    calls: dict[str, object] = {}

    selected = auto_trading_service.select_account_rotation_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-21T00:00:00Z",
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [],
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(
            policy_risk_on_score=0.70,
            policy_defensive_tilt=-0.01,
        ),
        fetch_news_features_fn=lambda _ticker: make_feature_bundle(
            news_sentiment_score=0.30,
            news_headline_count=6.0,
        ),
        fetch_social_features_fn=lambda _ticker: make_feature_bundle(
            social_trend_score=0.40,
            social_mention_count=5.0,
            social_reddit_sentiment=0.25,
        ),
        fetch_rotation_overlay_tickers_fn=lambda _conn, _account: calls.update({"overlay": True}) or ["AAPL"],
    )

    assert selected == "trend"
    assert calls == {"overlay": True}
