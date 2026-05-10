from __future__ import annotations

from trading.domain.rotation import dump_rotation_schedule
from trading.repositories.sleeves import (
    insert_sleeve_strategy_assignment,
    insert_strategy_sleeve,
    insert_strategy_param_set,
    set_strategy_param_set_activation,
)
from trading.services.accounts import get_account
from trading.services.sleeves.shadow_evaluation import (
    build_challenger_metrics_from_backtest_returns,
    build_sleeve_shadow_evaluation,
)
from tests.support.repositories import insert_repository_account


def test_build_challenger_metrics_from_backtest_returns_uses_active_param_set(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_shadow_metrics")
    param_set_id = insert_strategy_param_set(
        conn,
        strategy_name="meanrev",
        version="v1",
        params_json='{"lookback":20}',
        config_version="cfg-1",
        is_active=0,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        activated_at=None,
        deactivated_at=None,
        notes=None,
    )
    set_strategy_param_set_activation(
        conn,
        param_set_id=param_set_id,
        is_active=1,
        updated_at="2026-05-01T01:00:00Z",
        activated_at="2026-05-01T01:00:00Z",
        deactivated_at=None,
    )
    monkeypatch.setattr(
        "trading.services.sleeves.shadow_evaluation.fetch_strategy_backtest_returns",
        lambda *_args, **_kwargs: [("meanrev", 1.0), ("meanrev", -0.5), ("other", 5.0)],
    )

    metrics = build_challenger_metrics_from_backtest_returns(
        conn,
        account_id=account_id,
        strategy_name="meanrev",
        start_day="2026-04-01",
        end_day="2026-05-01",
    )

    assert metrics.strategy_name == "meanrev"
    assert metrics.param_set_id == param_set_id
    assert metrics.trade_count == 2
    assert metrics.risk_adjusted_return == 0.25
    assert metrics.stability == 0.5
    assert metrics.drawdown_penalty == 0.5


def test_build_sleeve_shadow_evaluation_returns_active_sleeve_candidates(conn, monkeypatch) -> None:
    account_name = "acct_shadow_eval"
    account_id = insert_repository_account(conn, name=account_name, strategy="trend")
    conn.execute(
        """
        UPDATE accounts
        SET rotation_schedule = ?
        WHERE id = ?
        """,
        (dump_rotation_schedule(["trend", "meanrev", "breakout"]), account_id),
    )
    conn.commit()
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core",
        status="active",
        base_ccy="USD",
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    account = get_account(conn, account_name)

    monkeypatch.setattr(
        "trading.services.sleeves.shadow_evaluation.fetch_strategy_backtest_returns",
        lambda _conn, *, account_id, strategy_names, start_day, end_day: [
            (strategy_names[0], 1.2),
            (strategy_names[0], 0.8),
        ],
    )

    result = build_sleeve_shadow_evaluation(
        conn,
        account=account,
        as_of_iso="2026-05-07T12:00:00Z",
        rolling_window_days=30,
    )

    assert result.account_name == account_name
    assert len(result.sleeves) == 1
    sleeve = result.sleeves[0]
    assert sleeve.sleeve_id == sleeve_id
    assert sleeve.incumbent_strategy == "trend"
    assert [item.strategy_name for item in sleeve.challengers] == ["meanrev", "breakout"]
    assert all(item.trade_count == 2 for item in sleeve.challengers)
