from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import trading.services.auto_trading.rotation as rotation_service
from tests.trading.services.auto_trading.factories import (
    make_auto_trading_account,
    make_feature_bundle,
    make_feature_fetcher,
)


def _account(**overrides):
    values: dict[str, object] = {
        "id": 7,
        "rotation_schedule": '["trend","mean_reversion"]',
        "rotation_lookback_days": 30,
        "rotation_optimality_mode": "hybrid_weighted",
        "rotation_enabled": 1,
        "rotation_last_at": "2026-03-01T00:00:00Z",
        "rotation_active_strategy": "trend",
        "rotation_active_index": 0,
        "initial_cash": 1000.0,
    }
    values.update(overrides)
    return make_auto_trading_account(**values)


def test_select_optimal_strategy_hybrid_weighted_prefers_better_live_signal() -> None:
    account = _account()
    fetch_returns = Mock(
        return_value=[
            ("trend", 10.0),
            ("mean_reversion", 9.0),
        ]
    )
    fetch_episodes = Mock(
        return_value=[
            {
                "strategy_name": "trend",
                "starting_equity": 1000.0,
                "ending_equity": 900.0,
            },
            {
                "strategy_name": "trend",
                "starting_equity": 1000.0,
                "ending_equity": 920.0,
            },
            {
                "strategy_name": "trend",
                "starting_equity": 1000.0,
                "ending_equity": 910.0,
            },
            {
                "strategy_name": "mean_reversion",
                "starting_equity": 1000.0,
                "ending_equity": 1200.0,
            },
            {
                "strategy_name": "mean_reversion",
                "starting_equity": 1000.0,
                "ending_equity": 1180.0,
            },
            {
                "strategy_name": "mean_reversion",
                "starting_equity": 1000.0,
                "ending_equity": 1190.0,
            },
        ]
    )

    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        fetch_strategy_backtest_returns_fn=fetch_returns,
        fetch_closed_rotation_episodes_fn=fetch_episodes,
    )

    assert selected == "mean_reversion"
    fetch_returns.assert_called_once()
    fetch_episodes.assert_called_once()


def test_select_optimal_strategy_hybrid_weighted_falls_back_to_backtest() -> None:
    account = _account()

    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        fetch_strategy_backtest_returns_fn=Mock(
            return_value=[
                ("trend", 10.0),
                ("mean_reversion", 8.0),
            ]
        ),
        fetch_closed_rotation_episodes_fn=Mock(return_value=[]),
    )

    assert selected == "trend"


def test_sync_rotation_episode_closes_previous_and_opens_new() -> None:
    account = _account(rotation_active_strategy="mean_reversion", rotation_active_index=1)
    closed_calls: list[dict[str, object]] = []
    inserted_calls: list[dict[str, object]] = []
    fetch_open_episode = Mock(
        return_value={
            "id": 11,
            "strategy_name": "trend",
            "started_at": "2026-03-01T00:00:00Z",
            "starting_realized_pnl": 5.0,
        }
    )

    with patch.object(
        rotation_service,
        "compute_live_account_metrics",
        Mock(return_value={"equity": 1125.0, "realized_pnl": 20.0}),
    ):
        rotation_service.sync_rotation_episode(
            conn=object(),
            account=account,
            as_of_iso="2026-03-20T00:00:00Z",
            fetch_open_rotation_episode_fn=fetch_open_episode,
            insert_rotation_episode_fn=lambda _conn, **kwargs: inserted_calls.append(kwargs),
            close_rotation_episode_fn=lambda _conn, **kwargs: closed_calls.append(kwargs),
            fetch_snapshot_count_between_fn=Mock(return_value=4),
            compute_live_account_metrics_fn=rotation_service.compute_live_account_metrics,
        )

    assert closed_calls == [
        {
            "episode_id": 11,
            "ended_at": "2026-03-20T00:00:00Z",
            "ending_equity": 1125.0,
            "ending_realized_pnl": 20.0,
            "realized_pnl_delta": 15.0,
            "snapshot_count": 4,
        }
    ]
    assert inserted_calls == [
        {
            "account_id": 7,
            "strategy_name": "mean_reversion",
            "started_at": "2026-03-20T00:00:00Z",
            "starting_equity": 1125.0,
            "starting_realized_pnl": 20.0,
        }
    ]


def test_select_regime_strategy_uses_policy_mapping() -> None:
    account = _account(
        rotation_schedule='["trend","ma_crossover","mean_reversion"]',
        rotation_active_strategy="trend",
        rotation_regime_strategy_risk_on="trend",
        rotation_regime_strategy_neutral="ma_crossover",
        rotation_regime_strategy_risk_off="mean_reversion",
    )

    selected = rotation_service.select_regime_strategy(
        account,
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(
            policy_risk_on_score=0.70,
            policy_defensive_tilt=-0.01,
        ),
    )

    assert selected == "trend"


def test_select_regime_strategy_keeps_active_when_features_unavailable() -> None:
    account = _account(
        rotation_schedule='["trend","ma_crossover","mean_reversion"]',
        rotation_active_strategy="ma_crossover",
        rotation_regime_strategy_risk_on="trend",
        rotation_regime_strategy_neutral="ma_crossover",
        rotation_regime_strategy_risk_off="mean_reversion",
    )

    selected = rotation_service.select_regime_strategy(
        account,
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(available=False),
    )

    assert selected == "ma_crossover"


def test_select_rotation_overlay_direction_requires_confident_majority() -> None:
    account = _account(
        rotation_overlay_min_tickers=2,
        rotation_overlay_confidence_threshold=0.5,
    )

    direction = rotation_service.select_rotation_overlay_direction(
        account,
        ["AAPL", "MSFT", "NVDA"],
        overlay_mode="news",
        fetch_news_features_fn=make_feature_fetcher(
            {
                "AAPL": {
                    "news_sentiment_score": 0.35,
                    "news_headline_count": 6.0,
                },
                "MSFT": {
                    "news_sentiment_score": 0.22,
                    "news_headline_count": 5.0,
                },
                "NVDA": {
                    "news_sentiment_score": -0.20,
                    "news_headline_count": 5.0,
                },
            }
        ),
        fetch_social_features_fn=None,
    )

    assert direction is None


def test_fetch_rotation_overlay_tickers_unions_holdings_and_watchlist() -> None:
    compute_account_state = Mock(
        return_value=SimpleNamespace(
            positions={"AAPL": 5.0, "MSFT": 0.0, "NVDA": 2.0},
        )
    )
    with (
        patch.object(rotation_service, "list_account_trades", Mock(return_value=[])),
        patch.object(
            rotation_service,
            "compute_account_state",
            compute_account_state,
        ),
    ):
        tickers = rotation_service.fetch_rotation_overlay_tickers(
            conn=object(),
            account=_account(
                rotation_overlay_watchlist='["msft","googl"]',
            ),
        )

    assert tickers == ["AAPL", "GOOGL", "MSFT", "NVDA"]
    compute_account_state.assert_called_once()


def test_select_regime_strategy_applies_bullish_news_overlay() -> None:
    account = _account(
        rotation_schedule='["trend","ma_crossover","mean_reversion"]',
        rotation_active_strategy="ma_crossover",
        rotation_regime_strategy_risk_on="trend",
        rotation_regime_strategy_neutral="ma_crossover",
        rotation_regime_strategy_risk_off="mean_reversion",
        rotation_overlay_mode="news",
        rotation_overlay_min_tickers=2,
        rotation_overlay_confidence_threshold=0.5,
    )

    selected = rotation_service.select_regime_strategy(
        account,
        conn=object(),
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(
            policy_risk_on_score=0.50,
            policy_defensive_tilt=0.0,
        ),
        fetch_news_features_fn=lambda _ticker: make_feature_bundle(
            news_sentiment_score=0.30,
            news_headline_count=6.0,
        ),
        fetch_social_features_fn=None,
        fetch_rotation_overlay_tickers_fn=Mock(return_value=["AAPL", "MSFT"]),
    )

    assert selected == "trend"


def test_select_rotation_overlay_direction_returns_bearish_with_confident_negative_votes() -> None:
    account = _account(
        rotation_overlay_min_tickers=2,
        rotation_overlay_confidence_threshold=0.5,
    )
    direction = rotation_service.select_rotation_overlay_direction(
        account,
        ["AAPL", "MSFT", "NVDA"],
        overlay_mode="news",
        fetch_news_features_fn=make_feature_fetcher(
                {
                    "AAPL": {"news_sentiment_score": -0.40, "news_headline_count": 6.0},
                    "MSFT": {"news_sentiment_score": -0.35, "news_headline_count": 5.0},
                    "NVDA": {"news_sentiment_score": 0.00, "news_headline_count": 5.0},
                }
            ),
            fetch_social_features_fn=None,
        )

    assert direction == "bearish"


def test_select_regime_strategy_keeps_active_when_resolved_strategy_not_in_schedule() -> None:
    account = _account(
        rotation_schedule='["trend","ma_crossover","mean_reversion"]',
        rotation_active_strategy="ma_crossover",
        rotation_regime_strategy_risk_on="breakout",
        rotation_regime_strategy_neutral="ma_crossover",
        rotation_regime_strategy_risk_off="mean_reversion",
    )
    selected = rotation_service.select_regime_strategy(
        account,
        fetch_policy_features_fn=lambda _ticker: make_feature_bundle(
            policy_risk_on_score=0.80,
            policy_defensive_tilt=-0.05,
        ),
    )

    assert selected == "ma_crossover"


def test_sync_rotation_episode_returns_early_when_rotation_disabled() -> None:
    close_rotation_episode = Mock()
    insert_rotation_episode = Mock()
    rotation_service.sync_rotation_episode(
        conn=object(),
        account=_account(rotation_enabled=0),
        as_of_iso="2026-03-20T00:00:00Z",
        fetch_open_rotation_episode_fn=Mock(return_value=None),
        insert_rotation_episode_fn=insert_rotation_episode,
        close_rotation_episode_fn=close_rotation_episode,
        fetch_snapshot_count_between_fn=Mock(return_value=0),
        compute_live_account_metrics_fn=Mock(return_value={"equity": 1000.0, "realized_pnl": 0.0}),
    )
    insert_rotation_episode.assert_not_called()
    close_rotation_episode.assert_not_called()


def test_compute_live_account_metrics_skips_price_fetch_when_no_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rotation_service,
        "compute_account_state",
        lambda *_args, **_kwargs: SimpleNamespace(cash=123.0, positions={}, avg_cost={}, realized_pnl=5.0),
    )
    monkeypatch.setattr(rotation_service, "list_account_trades", lambda *_args, **_kwargs: [])
    fetch_latest_prices = Mock()
    monkeypatch.setattr(rotation_service, "fetch_latest_prices", fetch_latest_prices)
    monkeypatch.setattr(rotation_service, "compute_market_value_and_unrealized", lambda *_a, **_k: (0.0, 0.0))

    metrics = rotation_service.compute_live_account_metrics(
        conn=object(),
        account=_account(),
    )

    assert metrics == {"equity": 123.0, "realized_pnl": 5.0}
    fetch_latest_prices.assert_not_called()


def test_coercion_and_classification_helpers_cover_invalid_inputs() -> None:
    assert rotation_service._coerce_threshold(2.0, default=0.5) == 0.5
    assert rotation_service.classify_policy_regime(risk_on_score=None, defensive_tilt=0.0) is None
    assert rotation_service.classify_policy_regime(risk_on_score=0.7, defensive_tilt=None) is None
    assert rotation_service._classify_news_overlay_vote(make_feature_bundle(available=False)) is None
    assert rotation_service._classify_news_overlay_vote(
        make_feature_bundle(news_sentiment_score=0.5, news_headline_count=1.0)
    ) is None
    assert rotation_service._classify_social_overlay_vote(
        make_feature_bundle(social_trend_score=-0.5, social_mention_count=3.0, social_reddit_sentiment=-0.2)
    ) == -1
    assert rotation_service._classify_social_overlay_vote(make_feature_bundle(available=False)) is None


def test_classify_social_overlay_vote_handles_missing_and_neutral_inputs() -> None:
    assert rotation_service._classify_social_overlay_vote(
        make_feature_bundle(social_trend_score=0.2, social_mention_count=5.0),
    ) is None
    assert rotation_service._classify_social_overlay_vote(
        make_feature_bundle(
            social_trend_score=0.0,
            social_mention_count=5.0,
            social_reddit_sentiment=0.1,
        ),
    ) == 0


def test_select_rotation_overlay_direction_returns_none_for_none_mode_or_empty_tickers() -> None:
    account = _account()
    assert (
        rotation_service.select_rotation_overlay_direction(
            account,
            [],
            overlay_mode="news",
            fetch_news_features_fn=lambda _ticker: make_feature_bundle(news_sentiment_score=0.4, news_headline_count=5.0),
            fetch_social_features_fn=None,
        )
        is None
    )
    assert (
        rotation_service.select_rotation_overlay_direction(
            account,
            ["AAPL"],
            overlay_mode="none",
            fetch_news_features_fn=lambda _ticker: make_feature_bundle(news_sentiment_score=0.4, news_headline_count=5.0),
            fetch_social_features_fn=None,
        )
        is None
    )


def test_select_rotation_overlay_direction_skips_tickers_without_votes() -> None:
    account = _account(
        rotation_overlay_min_tickers=1,
        rotation_overlay_confidence_threshold=0.5,
    )
    direction = rotation_service.select_rotation_overlay_direction(
        account,
        ["AAPL", "MSFT"],
        overlay_mode="news_social",
        fetch_news_features_fn=make_feature_fetcher(
            {
                "MSFT": {
                    "news_sentiment_score": 0.35,
                    "news_headline_count": 6.0,
                }
            }
        ),
        fetch_social_features_fn=make_feature_fetcher({}),
    )
    assert direction == "bullish"


def test_select_regime_strategy_returns_none_or_active_for_schedule_and_regime_edge_cases() -> None:
    assert (
        rotation_service.select_regime_strategy(
            _account(rotation_schedule="[]"),
            fetch_policy_features_fn=lambda _ticker: make_feature_bundle(policy_risk_on_score=0.8, policy_defensive_tilt=0.0),
        )
        is None
    )
    account = _account(rotation_active_strategy="trend")
    assert (
        rotation_service.select_regime_strategy(
            account,
            fetch_policy_features_fn=lambda _ticker: make_feature_bundle(policy_risk_on_score=None, policy_defensive_tilt=0.0),
        )
        == "trend"
    )
    assert (
        rotation_service.select_regime_strategy(
            _account(
                rotation_active_strategy="trend",
                rotation_regime_strategy_risk_on=None,
            ),
            fetch_policy_features_fn=lambda _ticker: make_feature_bundle(policy_risk_on_score=0.8, policy_defensive_tilt=0.0),
        )
        == "trend"
    )


def test_sync_rotation_episode_open_and_same_strategy_paths() -> None:
    inserted_calls: list[dict[str, object]] = []
    rotation_service.sync_rotation_episode(
        conn=object(),
        account=_account(),
        as_of_iso="2026-03-20T00:00:00Z",
        fetch_open_rotation_episode_fn=Mock(return_value=None),
        insert_rotation_episode_fn=lambda _conn, **kwargs: inserted_calls.append(kwargs),
        close_rotation_episode_fn=Mock(),
        fetch_snapshot_count_between_fn=Mock(return_value=0),
        compute_live_account_metrics_fn=Mock(return_value={"equity": 1010.0, "realized_pnl": 12.0}),
    )
    assert inserted_calls and inserted_calls[0]["strategy_name"] == "trend"

    close_rotation_episode = Mock()
    rotation_service.sync_rotation_episode(
        conn=object(),
        account=_account(rotation_active_strategy="trend"),
        as_of_iso="2026-03-20T00:00:00Z",
        fetch_open_rotation_episode_fn=Mock(
            return_value={"id": 1, "strategy_name": "trend", "started_at": "2026-03-01T00:00:00Z", "starting_realized_pnl": 0.0}
        ),
        insert_rotation_episode_fn=Mock(),
        close_rotation_episode_fn=close_rotation_episode,
        fetch_snapshot_count_between_fn=Mock(return_value=0),
        compute_live_account_metrics_fn=Mock(return_value={"equity": 1010.0, "realized_pnl": 12.0}),
    )
    close_rotation_episode.assert_not_called()


def test_sync_rotation_episode_returns_when_active_strategy_missing() -> None:
    insert_rotation_episode = Mock()
    with patch.object(rotation_service, "resolve_active_strategy", Mock(return_value=None)):
        rotation_service.sync_rotation_episode(
            conn=object(),
            account=_account(rotation_active_strategy=None, strategy=""),
            as_of_iso="2026-03-20T00:00:00Z",
            fetch_open_rotation_episode_fn=Mock(return_value=None),
            insert_rotation_episode_fn=insert_rotation_episode,
            close_rotation_episode_fn=Mock(),
            fetch_snapshot_count_between_fn=Mock(return_value=0),
            compute_live_account_metrics_fn=Mock(return_value={"equity": 1010.0, "realized_pnl": 12.0}),
        )
    insert_rotation_episode.assert_not_called()


def test_select_optimal_strategy_average_return_mode() -> None:
    account = _account(rotation_optimality_mode="average_return")
    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        fetch_strategy_backtest_returns_fn=Mock(
            return_value=[
                ("trend", 1.0),
                ("trend", 3.0),
                ("mean_reversion", 1.5),
                ("mean_reversion", 1.5),
            ]
        ),
        fetch_closed_rotation_episodes_fn=None,
    )
    assert selected == "trend"


def test_rotate_account_if_due_uses_index_fallback_when_selected_not_in_schedule() -> None:
    account = _account(rotation_mode="optimal", rotation_active_index=1, rotation_schedule='["trend","mean_reversion"]')
    updated_rows: list[dict[str, object]] = []
    updated = rotation_service.rotate_account_if_due(
        conn=object(),
        account_name="acct",
        account=account,
        now_iso="2026-03-31T00:00:00Z",
        is_rotation_due_fn=lambda _account: True,
        select_optimal_strategy_fn=lambda *_args, **_kwargs: "outside_schedule",
        update_account_rotation_state_fn=lambda _conn, **kwargs: updated_rows.append(kwargs),
        get_account_fn=lambda _conn, _name: account,
    )
    assert updated is account
    assert updated_rows[0]["rotation_active_index"] == 1


def test_select_optimal_strategy_hybrid_weighted_uses_live_score_when_backtest_missing() -> None:
    account = _account()
    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        fetch_strategy_backtest_returns_fn=Mock(return_value=[("trend", 1.0)]),
        fetch_closed_rotation_episodes_fn=Mock(
            return_value=[
                {
                    "strategy_name": "mean_reversion",
                    "starting_equity": 1000.0,
                    "ending_equity": 1200.0,
                }
            ]
        ),
    )
    assert selected == "mean_reversion"


def test_select_optimal_strategy_hybrid_weighted_returns_none_when_truthy_empty_returns_and_invalid_live_rows() -> None:
    class _TruthyEmptyReturns:
        def __bool__(self):
            return True

        def __iter__(self):
            return iter(())

    account = _account()
    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        fetch_strategy_backtest_returns_fn=Mock(return_value=_TruthyEmptyReturns()),
        fetch_closed_rotation_episodes_fn=Mock(
            return_value=[
                {"strategy_name": "trend", "starting_equity": None, "ending_equity": 1000.0},
                {"strategy_name": "mean_reversion", "starting_equity": 0.0, "ending_equity": 1000.0},
            ]
        ),
    )
    assert selected is None
