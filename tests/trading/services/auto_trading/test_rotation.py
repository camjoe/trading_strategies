from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import trading.services.auto_trading.rotation as rotation_service
from tests.support import make_auto_trading_account, make_feature_bundle, make_feature_fetcher


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
        fetch_strategy_backtest_returns_fn=Mock(return_value=[
            ("trend", 10.0),
            ("mean_reversion", 8.0),
        ]),
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

    rotation_service.sync_rotation_episode(
        conn=object(),
        account=account,
        as_of_iso="2026-03-20T00:00:00Z",
        resolve_active_strategy_fn=lambda row: str(row["rotation_active_strategy"]),
        fetch_open_rotation_episode_fn=fetch_open_episode,
        insert_rotation_episode_fn=lambda _conn, **kwargs: inserted_calls.append(kwargs),
        close_rotation_episode_fn=lambda _conn, **kwargs: closed_calls.append(kwargs),
        fetch_snapshot_count_between_fn=Mock(return_value=4),
        compute_live_account_metrics_fn=Mock(return_value={"equity": 1125.0, "realized_pnl": 20.0}),
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
    tickers = rotation_service.fetch_rotation_overlay_tickers(
        conn=object(),
        account=_account(
            rotation_overlay_watchlist='["msft","googl"]',
        ),
        load_trades_fn=Mock(return_value=[]),
        compute_account_state_fn=compute_account_state,
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
