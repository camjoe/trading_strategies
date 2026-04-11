from __future__ import annotations

from types import SimpleNamespace

from trading.domain.rotation import parse_rotation_schedule

import trading.services.rotation_service as rotation_service


def _account(**overrides):
    account = {
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
    account.update(overrides)
    return account


def test_select_optimal_strategy_hybrid_weighted_prefers_better_live_signal() -> None:
    account = _account()

    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=rotation_service.parse_as_of_iso,
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [
            ("trend", 10.0),
            ("mean_reversion", 9.0),
        ],
        resolve_optimality_mode_fn=lambda row: str(row["rotation_optimality_mode"]),
        fetch_closed_rotation_episodes_fn=lambda *_args, **_kwargs: [
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
        ],
    )

    assert selected == "mean_reversion"


def test_select_optimal_strategy_hybrid_weighted_falls_back_to_backtest() -> None:
    account = _account()

    selected = rotation_service.select_optimal_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-31T00:00:00Z",
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=rotation_service.parse_as_of_iso,
        fetch_strategy_backtest_returns_fn=lambda *_args, **_kwargs: [
            ("trend", 10.0),
            ("mean_reversion", 8.0),
        ],
        resolve_optimality_mode_fn=lambda row: str(row["rotation_optimality_mode"]),
        fetch_closed_rotation_episodes_fn=lambda *_args, **_kwargs: [],
    )

    assert selected == "trend"


def test_sync_rotation_episode_closes_previous_and_opens_new() -> None:
    account = _account(rotation_active_strategy="mean_reversion", rotation_active_index=1)
    closed_calls: list[dict[str, object]] = []
    inserted_calls: list[dict[str, object]] = []

    rotation_service.sync_rotation_episode(
        conn=object(),
        account=account,
        as_of_iso="2026-03-20T00:00:00Z",
        resolve_active_strategy_fn=lambda row: str(row["rotation_active_strategy"]),
        fetch_open_rotation_episode_fn=lambda *_args, **_kwargs: {
            "id": 11,
            "strategy_name": "trend",
            "started_at": "2026-03-01T00:00:00Z",
            "starting_realized_pnl": 5.0,
        },
        insert_rotation_episode_fn=lambda _conn, **kwargs: inserted_calls.append(kwargs),
        close_rotation_episode_fn=lambda _conn, **kwargs: closed_calls.append(kwargs),
        fetch_snapshot_count_between_fn=lambda *_args, **_kwargs: 4,
        compute_live_account_metrics_fn=lambda _conn, _account: {"equity": 1125.0, "realized_pnl": 20.0},
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
        parse_rotation_schedule_fn=parse_rotation_schedule,
        resolve_active_strategy_fn=lambda row: str(row["rotation_active_strategy"]),
        resolve_rotation_regime_strategy_fn=lambda row, state: row[f"rotation_regime_strategy_{state}"],
        fetch_policy_features_fn=lambda _ticker: SimpleNamespace(
            available=True,
            get=lambda key, default=None: {
                "policy_risk_on_score": 0.70,
                "policy_defensive_tilt": -0.01,
            }.get(key, default),
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
        parse_rotation_schedule_fn=parse_rotation_schedule,
        resolve_active_strategy_fn=lambda row: str(row["rotation_active_strategy"]),
        resolve_rotation_regime_strategy_fn=lambda row, state: row[f"rotation_regime_strategy_{state}"],
        fetch_policy_features_fn=lambda _ticker: SimpleNamespace(
            available=False,
            get=lambda _key, default=None: default,
        ),
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
        fetch_news_features_fn=lambda ticker: SimpleNamespace(
            available=True,
            get=lambda key, default=None: {
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
            }[ticker].get(key, default),
        ),
        fetch_social_features_fn=None,
    )

    assert direction is None


def test_fetch_rotation_overlay_tickers_unions_holdings_and_watchlist() -> None:
    tickers = rotation_service.fetch_rotation_overlay_tickers(
        conn=object(),
        account=_account(
            rotation_overlay_watchlist='["msft","googl"]',
        ),
        load_trades_fn=lambda *_args, **_kwargs: [],
        compute_account_state_fn=lambda _cash, _trades: SimpleNamespace(
            positions={"AAPL": 5.0, "MSFT": 0.0, "NVDA": 2.0},
        ),
    )

    assert tickers == ["AAPL", "GOOGL", "MSFT", "NVDA"]


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
        parse_rotation_schedule_fn=parse_rotation_schedule,
        resolve_active_strategy_fn=lambda row: str(row["rotation_active_strategy"]),
        resolve_rotation_regime_strategy_fn=lambda row, state: row[f"rotation_regime_strategy_{state}"],
        fetch_policy_features_fn=lambda _ticker: SimpleNamespace(
            available=True,
            get=lambda key, default=None: {
                "policy_risk_on_score": 0.50,
                "policy_defensive_tilt": 0.0,
            }.get(key, default),
        ),
        fetch_news_features_fn=lambda _ticker: SimpleNamespace(
            available=True,
            get=lambda key, default=None: {
                "news_sentiment_score": 0.30,
                "news_headline_count": 6.0,
            }.get(key, default),
        ),
        fetch_social_features_fn=None,
        fetch_rotation_overlay_tickers_fn=lambda _conn, _account: ["AAPL", "MSFT"],
    )

    assert selected == "trend"
