from __future__ import annotations

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
