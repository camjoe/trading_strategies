from __future__ import annotations

import types

import pytest

from trading.services.operational_settings.models import RuntimeThrottleSettings
from trading.domain.evaluation_confidence import EvaluationConfidenceSettings
from trading.interfaces.cli.handlers.settings_handlers import (
    handle_configure_book_rotation,
    handle_configure_book_rotation_policy,
    handle_configure_evaluation,
    handle_configure_promotion,
    handle_configure_throttle,
)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def test_handle_configure_throttle_merges_over_current(capsys) -> None:
    calls: dict = {}
    deps = {
        "fetch_runtime_throttle_settings": lambda _conn: RuntimeThrottleSettings(
            max_trades_per_day=10, max_trades_per_minute=2
        ),
        "set_runtime_throttle_settings": lambda _conn, **kwargs: calls.update(kwargs),
    }

    handle_configure_throttle(
        object(),
        types.SimpleNamespace(max_trades_per_day=25),
        _parser(),
        deps=deps,
    )

    assert calls["runtime_max_trades_per_day"] == 25
    assert calls["runtime_max_trades_per_minute"] == 2
    assert "max_trades_per_day=25" in capsys.readouterr().out


def test_handle_configure_evaluation_merges_partial_flags(capsys) -> None:
    calls: dict = {}
    deps = {
        "fetch_evaluation_confidence_settings": lambda _conn: EvaluationConfidenceSettings(),
        "set_evaluation_confidence_settings": lambda _conn, **kwargs: calls.update(kwargs),
    }

    handle_configure_evaluation(
        object(),
        types.SimpleNamespace(backtest_evidence_weight=0.7, paper_live_evidence_weight=0.3),
        _parser(),
        deps=deps,
    )

    assert calls["backtest_evidence_weight"] == 0.7
    assert calls["paper_live_evidence_weight"] == 0.3
    defaults = EvaluationConfidenceSettings()
    assert calls["backtest_trade_count_for_full_confidence"] == defaults.backtest_trade_count_for_full_confidence
    assert "backtest_evidence_weight=0.7" in capsys.readouterr().out


def test_handle_configure_book_rotation_policy_passes_only_provided_flags(capsys) -> None:
    calls: dict = {}

    def fake_update(_conn, *, account_name, book_name, updates):
        calls.update({"account_name": account_name, "book_name": book_name, "updates": dict(updates)})
        return types.SimpleNamespace(
            book_id=7,
            min_trades_in_window=None,
            outperformance_threshold_bps=None,
            cooldown_days=10,
            risk_adjusted_return_weight=None,
            stability_weight=0.4,
            drawdown_penalty_weight=None,
            cost_penalty_weight=None,
            regime_fit_weight=None,
        )

    handle_configure_book_rotation_policy(
        object(),
        types.SimpleNamespace(account="acct1", book=None, cooldown_days=10, stability_weight=0.4),
        _parser(),
        deps={"update_book_rotation_policy": fake_update},
    )

    assert calls["account_name"] == "acct1"
    assert calls["book_name"] is None
    assert calls["updates"] == {"cooldown_days": 10, "stability_weight": 0.4}
    out = capsys.readouterr().out
    assert "book_id=7" in out
    assert "cooldown_days=10" in out


def test_handle_configure_book_rotation_policy_requires_a_flag() -> None:
    with pytest.raises(SystemExit):
        handle_configure_book_rotation_policy(
            object(),
            types.SimpleNamespace(account="acct1", book=None),
            _parser(),
            deps={},
        )


@pytest.mark.parametrize(
    "handler",
    [handle_configure_throttle, handle_configure_evaluation, handle_configure_promotion],
)
def test_global_configure_handlers_require_a_flag(handler) -> None:
    # A zero-flag invocation must error rather than silently persisting the
    # current effective values (which would pin code defaults into the DB).
    with pytest.raises(SystemExit):
        handler(object(), types.SimpleNamespace(), _parser(), deps={})


def test_handle_configure_book_rotation_maps_flags_to_fields(capsys) -> None:
    calls: dict = {}

    def fake_update(_conn, *, account_name, book_name, updates):
        calls.update({"account_name": account_name, "book_name": book_name, "updates": dict(updates)})
        return types.SimpleNamespace(
            book_id=9,
            rotation_enabled=1,
            rotation_schedule='["trend","meanrev"]',
            rotation_lookback_days=None,
        )

    handle_configure_book_rotation(
        object(),
        types.SimpleNamespace(account="acct1", book=None, enabled=True, schedule=["trend", "meanrev"]),
        _parser(),
        deps={"update_book_rotation_scheduling": fake_update},
    )

    assert calls["account_name"] == "acct1"
    assert calls["updates"] == {"rotation_enabled": True, "rotation_schedule": ["trend", "meanrev"]}
    out = capsys.readouterr().out
    assert "book_id=9" in out
    assert "rotation_lookback_days=none" in out


def test_handle_configure_book_rotation_requires_a_flag() -> None:
    with pytest.raises(SystemExit):
        handle_configure_book_rotation(
            object(),
            types.SimpleNamespace(account="acct1", book=None),
            _parser(),
            deps={},
        )
