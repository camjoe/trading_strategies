from unittest.mock import Mock

import pytest

from trading.domain.feature_provider import FeatureFetcherSet
from trading.interfaces.runtime.jobs.run_auto_trades import run_for_account
import trading.services.auto_trading.execution as execution_service
import trading.services.auto_trading.runtime as runtime_service
import trading.services.auto_trading.runtime_rotation as rotation_runtime_service
from tests.trading.services.auto_trading.factories import (
    RuntimeScenario,
    make_account_state,
    make_auto_trading_account,
)


def test_runtime_rotation_passthrough_helpers_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=7)
    conn = object()
    overlay_calls: list[tuple[object, object]] = []
    metric_calls: list[tuple[object, object]] = []

    monkeypatch.setattr(
        rotation_runtime_service,
        "fetch_rotation_overlay_tickers_impl",
        lambda inner_conn, inner_account: overlay_calls.append((inner_conn, inner_account)) or ["QQQ"],
    )
    monkeypatch.setattr(
        rotation_runtime_service,
        "compute_live_account_metrics_impl",
        lambda inner_conn, inner_account: metric_calls.append((inner_conn, inner_account)) or {"equity": 123.0},
    )

    assert rotation_runtime_service.fetch_runtime_rotation_overlay_tickers(conn, account) == ["QQQ"]
    assert rotation_runtime_service.compute_runtime_live_account_metrics(conn, account) == {"equity": 123.0}
    assert overlay_calls == [(conn, account)]
    assert metric_calls == [(conn, account)]


def test_select_runtime_rotation_strategy_passes_runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=12)
    calls: dict[str, object] = {}
    fetch_backtests = Mock(return_value=[])
    fetch_closed_episodes = Mock(return_value=[])
    feature_fetchers = FeatureFetcherSet(fetch_policy=Mock(), fetch_news=Mock(), fetch_social=Mock())

    def _fake_select(conn, selected_account, as_of_iso, **kwargs):
        calls.update(
            {
                "conn": conn,
                "account": selected_account,
                "as_of_iso": as_of_iso,
                **kwargs,
            }
        )
        return "mean_reversion"

    monkeypatch.setattr(rotation_runtime_service, "select_account_rotation_strategy_impl", _fake_select)

    selected = rotation_runtime_service.select_runtime_rotation_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-21T00:00:00Z",
        feature_fetchers=feature_fetchers,
        fetch_strategy_backtest_returns_fn=fetch_backtests,
        fetch_closed_rotation_episodes_fn=fetch_closed_episodes,
    )

    assert selected == "mean_reversion"
    assert calls["account"] == account
    assert calls["fetch_strategy_backtest_returns_fn"] is fetch_backtests
    assert calls["fetch_closed_rotation_episodes_fn"] is fetch_closed_episodes
    assert calls["fetch_policy_features_fn"] is feature_fetchers.fetch_policy
    assert calls["fetch_news_features_fn"] is feature_fetchers.fetch_news
    assert calls["fetch_social_features_fn"] is feature_fetchers.fetch_social
    assert (
        calls["fetch_rotation_overlay_tickers_fn"] is rotation_runtime_service.fetch_runtime_rotation_overlay_tickers
    )


def test_sync_runtime_rotation_episode_requires_connection_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=13)
    recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _fake_sync(*args, **kwargs) -> None:
        recorded.append((args, kwargs))

    monkeypatch.setattr(rotation_runtime_service, "sync_rotation_episode_impl", _fake_sync)

    rotation_runtime_service.sync_runtime_rotation_episode(
        object(),
        account,
        "2026-03-21T00:00:00Z",
        fetch_open_rotation_episode_fn=Mock(),
        insert_rotation_episode_fn=Mock(),
        close_rotation_episode_fn=Mock(),
        fetch_snapshot_count_between_fn=Mock(),
    )

    class _Conn:
        def execute(self, *_args, **_kwargs) -> None:
            return None

    connection = _Conn()
    fetch_open = Mock()
    insert_episode = Mock()
    close_episode = Mock()
    fetch_snapshot_count = Mock()
    rotation_runtime_service.sync_runtime_rotation_episode(
        connection,
        account,
        "2026-03-22T00:00:00Z",
        fetch_open_rotation_episode_fn=fetch_open,
        insert_rotation_episode_fn=insert_episode,
        close_rotation_episode_fn=close_episode,
        fetch_snapshot_count_between_fn=fetch_snapshot_count,
    )

    assert len(recorded) == 1
    args, kwargs = recorded[0]
    assert args[:3] == (connection, account, "2026-03-22T00:00:00Z")
    assert kwargs["fetch_open_rotation_episode_fn"] is fetch_open
    assert kwargs["insert_rotation_episode_fn"] is insert_episode
    assert kwargs["close_rotation_episode_fn"] is close_episode
    assert kwargs["fetch_snapshot_count_between_fn"] is fetch_snapshot_count
    assert kwargs["compute_live_account_metrics_fn"] is rotation_runtime_service.compute_runtime_live_account_metrics


def test_rotate_runtime_account_syncs_before_and_after_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=14, strategy="trend")
    rotated_account = make_auto_trading_account(id=14, strategy="mean_reversion")
    sync_calls: list[object] = []
    selection_calls: list[dict[str, object]] = []
    update_rotation_state = Mock()
    get_account = Mock(return_value=rotated_account)
    is_rotation_due = Mock(return_value=True)
    fetch_backtests = Mock(return_value=[])
    fetch_closed_episodes = Mock(return_value=[])
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        rotation_runtime_service,
        "sync_runtime_rotation_episode",
        lambda _conn, synced_account, _now_iso, **_kwargs: sync_calls.append(synced_account),
    )

    def _fake_select(conn, selected_account, as_of_iso, **kwargs):
        selection_calls.append(kwargs)
        assert conn is observed["conn"]
        assert selected_account == account
        assert as_of_iso == "2026-03-23T00:00:00Z"
        return "mean_reversion"

    def _fake_rotate(conn, account_name, current_account, now_iso, deps):
        observed["conn"] = conn
        observed["due"] = deps.is_rotation_due_fn(current_account)
        observed["selected"] = deps.select_optimal_strategy_fn(conn, current_account, now_iso)
        observed["refetched"] = deps.get_account_fn(conn, account_name)
        observed["update_fn"] = deps.update_account_rotation_state_fn
        return rotated_account

    monkeypatch.setattr(rotation_runtime_service, "select_runtime_rotation_strategy", _fake_select)
    monkeypatch.setattr(rotation_runtime_service, "rotate_runtime_account_if_due_impl", _fake_rotate)

    rotated = rotation_runtime_service.rotate_runtime_account(
        conn=object(),
        account_name="acct_runtime",
        account=account,
        now_iso="2026-03-23T00:00:00Z",
        feature_fetchers=FeatureFetcherSet(fetch_policy=Mock(), fetch_news=Mock(), fetch_social=Mock()),
        is_rotation_due_fn=is_rotation_due,
        update_account_rotation_state_fn=update_rotation_state,
        get_account_fn=get_account,
        fetch_strategy_backtest_returns_fn=fetch_backtests,
        fetch_closed_rotation_episodes_fn=fetch_closed_episodes,
        fetch_open_rotation_episode_fn=Mock(),
        insert_rotation_episode_fn=Mock(),
        close_rotation_episode_fn=Mock(),
        fetch_snapshot_count_between_fn=Mock(),
    )

    assert rotated == rotated_account
    assert sync_calls == [account, rotated_account]
    assert observed["due"] is True
    assert observed["selected"] == "mean_reversion"
    assert observed["refetched"] == rotated_account
    assert observed["update_fn"] is update_rotation_state
    assert selection_calls[0]["fetch_strategy_backtest_returns_fn"] is fetch_backtests
    assert selection_calls[0]["fetch_closed_rotation_episodes_fn"] is fetch_closed_episodes


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
        broker_factory=Mock(return_value=scenario.broker),
        feature_fetchers=FeatureFetcherSet(fetch_policy=Mock()),
    )

    assert executed == 1
    args, _kwargs = scenario.trade_recorder.call_args
    assert args[6] == "mean_reversion"
